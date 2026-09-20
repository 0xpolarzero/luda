/** Luda cooperating ProseMirror read-only bridge, version 1.
 * Import in the application's build; never inject into an existing user profile.
 */
const registrations = new Map();
const registry = Object.freeze({version: 1, list: () => [...registrations.values()], get: id => registrations.get(id)});
if (Object.hasOwn(window, '__ludaProseMirror')) throw new Error('Luda bridge already registered');
Object.defineProperty(window, '__ludaProseMirror', {value: registry, configurable: false});

export function registerProseMirror(view, {paragraphs, hard_breaks} = {}) {
  if (hard_breaks !== undefined && hard_breaks !== 'shift-enter') throw new Error('Declare native Shift+Enter hard-break behavior');
  const breaks = hard_breaks === 'shift-enter';
  if (breaks && !(view?.state?.schema?.nodes?.hard_break?.isInline && view.state.schema.nodes.hard_break.isLeaf)) throw new Error('Hard-break schema node required');
  if (paragraphs !== 'enter') throw new Error('Declare native Enter paragraph behavior');
  if (!view?.dom || !view?.state?.doc || registrations.size >= 32) throw new Error('Invalid or excessive editor registrations');
  const root = view.dom, id = crypto.randomUUID();
  if ([...registrations.values()].some(entry => entry.root === root)) throw new Error('Editor already registered');
  const entry = Object.freeze({id, root, contract: breaks ? 'basic-paragraphs-hard-breaks-v1' : 'basic-paragraphs-v1',
    identity: () => view.state.doc,
    at(offset) {
      if (!Number.isInteger(offset) || offset < 0) return null;
      let logical=0, position=0;
      for (let i=0;i<view.state.doc.childCount;i++) {
        const paragraph=view.state.doc.child(i);
        let native=position+1;
        if (offset===logical) {const dom=view.domAtPos(native);return {...dom,position:native,roundtrip:view.posAtDOM(dom.node,dom.offset,1)};}
        for (let j=0;j<paragraph.childCount;j++) {
          const child=paragraph.child(j);
          if (child.isText) {
            for (const char of child.text) {
              native+=char.length;logical++;
              if (offset===logical) {const dom=view.domAtPos(native);return {...dom,position:native,roundtrip:view.posAtDOM(dom.node,dom.offset,1)};}
            }
          } else if (breaks && child.type.name==='hard_break') {
            native+=child.nodeSize;logical++;
            if (offset===logical) {const dom=view.domAtPos(native);return {...dom,position:native,roundtrip:view.posAtDOM(dom.node,dom.offset,1)};}
          } else return null;
        }
        logical++;position+=paragraph.nodeSize;
      }
      return null;
    }, read() {
    if (view.isDestroyed || view.dom !== root || !root.isConnected || root.getRootNode() !== document) return {error:'STALE_TARGET'};
    if (view.state.storedMarks?.some(mark=>!['strong','em'].includes(mark.type.name)||Object.keys(mark.attrs).length)) return {error:'TEXT_REPRESENTATION_UNSUPPORTED'};
    const doc = view.state.doc;
    if (doc.content.size > 128000 || doc.childCount > 128) return {error:'VERIFICATION_LIMIT'};
    let nodes = 0, unsupported = doc.type.name !== 'doc';
    doc.descendants((node, pos, parent) => {
      if (++nodes > 4096) return false;
      if (!(node.type.name === 'paragraph' && parent === doc || (node.isText || breaks && node.type.name === 'hard_break' && node.isLeaf && node.nodeSize === 1) && parent.type.name === 'paragraph')) unsupported = true;
      if (Object.keys(node.attrs).length || node.marks.some(mark => !['strong','em'].includes(mark.type.name) || Object.keys(mark.attrs).length)) unsupported = true;
      return !unsupported;
    });
    if (nodes > 4096) return {error:'VERIFICATION_LIMIT'};
    if (unsupported || Object.keys(doc.attrs).length) return {error:'TEXT_REPRESENTATION_UNSUPPORTED'};
    const model = doc.toJSON();
    if (JSON.stringify(model).length > 128000) return {error:'VERIFICATION_LIMIT'};
    const rect=root.getBoundingClientRect(), style=getComputedStyle(root);
    return {contract:entry.contract,model, selection: view.state.selection.toJSON(), stored_marks: view.state.storedMarks?.map(mark=>mark.toJSON()) ?? null,
      visible:rect.width>0&&rect.height>0&&style.visibility==='visible'&&style.display!=='none',
      enabled:view.editable && !root.closest('[inert]'), focused:document.hasFocus()&&document.activeElement===root,
      composition:window.__ludaOwnedComposition??{known:false,active:null}};
  }});
  registrations.set(id, entry);
  return () => {if(registrations.get(id) === entry) registrations.delete(id);};
}
