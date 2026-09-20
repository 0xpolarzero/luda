"""Backend availability is distinct from a particular application's capability."""


def capability_summary(report):
    dependencies=report['dependencies']
    display=report['display_available']
    blocked=(report['session_state']['input_ready'] is False or
             report['control'].get('paused') is True or
             report['control'].get('available') is False)
    def input_state(available, semantic=False):
        if not available:return 'unavailable'
        if blocked:return 'blocked'
        return 'application_dependent' if semantic else 'backend_available'
    return {
        'screen_observation':'backend_available' if display and dependencies.get('scrot') else 'unavailable',
        'pointer_input':input_state(display and dependencies.get('xdotool')),
        'keyboard_input':input_state(display and report['keyboard']['available']),
        'clipboard_paste':input_state(display and report['keyboard']['available'] and dependencies.get('xclip')),
        'accessibility_read':'backend_available' if display and report['accessibility_available'] else 'unavailable',
        'verified_text_editing':input_state(display and report['accessibility_available'],semantic=True),
        'ime_composition':'unsupported',
    }
