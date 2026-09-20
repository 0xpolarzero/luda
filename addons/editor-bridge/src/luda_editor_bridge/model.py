"""Bounded basic-paragraph model validation and exact content/mark comparison."""
import json


class RichInvalid(ValueError):
    def __init__(self, code): self.code=code


def decode(value):
    contract=value.get('contract','basic-paragraphs-v1')
    if contract not in ('basic-paragraphs-v1','basic-paragraphs-hard-breaks-v1'):raise RichInvalid('TEXT_REPRESENTATION_UNSUPPORTED')
    hard_breaks=contract=='basic-paragraphs-hard-breaks-v1'
    pending=value.get('stored_marks')
    if pending is not None and (not isinstance(pending,list) or any(not isinstance(mark,dict) or set(mark)!={'type'} or mark['type'] not in ('strong','em') for mark in pending)):
        raise RichInvalid('TEXT_REPRESENTATION_UNSUPPORTED')
    model=value.get('model')
    if not isinstance(model,dict) or model.get('type')!='doc' or set(model)-{'type','content'}:
        raise RichInvalid('TEXT_REPRESENTATION_UNSUPPORTED')
    paragraphs=model.get('content')
    if not isinstance(paragraphs,list) or not 1<=len(paragraphs)<=128:
        raise RichInvalid('VERIFICATION_LIMIT')
    if len(json.dumps(model,ensure_ascii=False).encode())>512000:
        raise RichInvalid('VERIFICATION_LIMIT')
    texts=[]; styled=[]; layout=[]; offsets={};position=0;logical=0;nodes=0
    for index,paragraph in enumerate(paragraphs):
        if not isinstance(paragraph,dict) or paragraph.get('type')!='paragraph' or set(paragraph)-{'type','content'}:
            raise RichInvalid('TEXT_REPRESENTATION_UNSUPPORTED')
        content=paragraph.get('content',[])
        if not isinstance(content,list):raise RichInvalid('TEXT_REPRESENTATION_UNSUPPORTED')
        text='';marks=[];native=position+1;offsets[native]=logical
        for node in content:
            nodes+=1
            if nodes>4096:raise RichInvalid('VERIFICATION_LIMIT')
            is_break=isinstance(node,dict) and node.get('type')=='hard_break' and hard_breaks
            if not isinstance(node,dict) or (set(node)-{'type','marks'} if is_break else node.get('type')!='text' or set(node)-{'type','text','marks'} or not isinstance(node.get('text'),str)):
                raise RichInvalid('TEXT_REPRESENTATION_UNSUPPORTED')
            formatting=node.get('marks',[])
            if not isinstance(formatting,list) or any(not isinstance(m,dict) or set(m)!={'type'} or m['type'] not in ('strong','em') for m in formatting):
                raise RichInvalid('TEXT_REPRESENTATION_UNSUPPORTED')
            if is_break:
                text+='\n';marks.append(('hard_break',tuple(m['type'] for m in formatting)));layout.append('h');native+=1;logical+=1;offsets[native]=logical
                continue
            for char in node['text']:
                if char in '\r\n\x00' or 0xD800<=ord(char)<=0xDFFF:raise RichInvalid('TEXT_REPRESENTATION_UNSUPPORTED')
                text+=char;marks.append(tuple(m['type'] for m in formatting));layout.append('t');native+=2 if ord(char)>0xFFFF else 1
                logical+=1;offsets[native]=logical
                if logical>64000:raise RichInvalid('VERIFICATION_LIMIT')
        texts.append(text);styled.extend(marks)
        position=native+1
        if index<len(paragraphs)-1:styled.append(None);layout.append('p');logical+=1
    if logical>64000:raise RichInvalid('VERIFICATION_LIMIT')
    selection=value.get('selection',{})
    if selection.get('type')=='text':
        anchor=selection.get('anchor');head=selection.get('head')
        start=offsets.get(min(anchor,head)) if type(anchor) is int and type(head) is int else None
        end=offsets.get(max(anchor,head)) if type(anchor) is int and type(head) is int else None
    elif selection.get('type')=='all':start,end=0,logical;anchor,head=0,position
    else:start=end=anchor=head=None
    return {**value,'text':'\n'.join(texts),'styled':styled,'start':start,'end':end,
            'direction':'backward' if anchor is not None and head is not None and anchor>head else 'forward',
            'paragraphs':texts,'layout':''.join(layout),'hard_breaks_supported':hard_breaks,'tag':'PROSEMIRROR','type':contract}


def unchanged_prefix(before, after):
    """Compare existing characters, marks and paragraph separators without run merging assumptions."""
    return after['text'].startswith(before['text']) and after['styled'][:len(before['styled'])]==before['styled']


def insertion_layout(text, line_breaks):
    return ''.join(('h' if line_breaks=='hard_break' else 'p') if char=='\n' else 't' for char in text)


def layout_over_budget(layout):
    # Paragraphs, leaf breaks and separated text runs cannot merge.
    # App-chosen mark fragmentation may require additional nodes after input.
    paragraphs=layout.count('p')+1
    text_runs=sum(kind=='t' and (i==0 or layout[i-1]!='t') for i,kind in enumerate(layout))
    return paragraphs>128 or paragraphs+layout.count('h')+text_runs>4096
