from luda.browser import OwnedBrowser as Browser, MESSAGES
from .progress import rich_text_progress

class OwnedBrowser(Browser):
    guard_module = "luda_editor_bridge.guard"
    supported_fields = "explicitly registered supported ProseMirror editors"
    messages = {**MESSAGES, **{'LINE_BREAK_SEMANTICS_REQUIRED': 'Specify one supported line_breaks policy for LF (paragraph or explicitly declared hard_break); no input sent.', 'FORMATTING_CHANGED': 'Existing rich-text formatting changed after input; inspect before retrying.', 'TEXT_REPRESENTATION_UNSUPPORTED': 'This editor contains unsupported structure or marks; no exact text route is available.'}}

    def receipt_progress(self, value, args):
        return rich_text_progress(value, len(args["text"].split("\n"))) if isinstance(args.get("text"), str) else None
