/* Test-only opt-in GTK3 signal observer. No text getter, injection or IPC API. */
#include <gtk/gtk.h>
#include <gmodule.h>
#include <unistd.h>
#include <stdlib.h>

typedef struct { guint64 generation; gboolean known, active; } Context;
static GHashTable *contexts;
static guint64 next_generation, sequence;
static int output_fd = -1;

static void publish(const char *event, Context *context) {
    guint active = 0;
    GHashTableIter it; gpointer value;
    g_hash_table_iter_init(&it, contexts);
    while (g_hash_table_iter_next(&it, NULL, &value)) {
        Context *item = value;
        if (item->known && item->active) active++;
    }
    /* A zero count cannot prove absence of an unobserved active context. */
    char buffer[768];
    int length = g_snprintf(buffer, sizeof buffer,
      "{\"sequence\":%" G_GUINT64_FORMAT ",\"event\":\"%s\",\"context_generation\":%" G_GUINT64_FORMAT
      ",\"context_known\":%s,\"context_active\":%s,\"observed_active_contexts\":%u,"
      "\"process_known\":%s,\"process_active\":%s,\"field_identity_known\":false}\n",
      ++sequence, event, context ? context->generation : 0,
      context && context->known ? "true" : "false",
      context && context->known ? (context->active ? "true" : "false") : "null",
      active, active ? "true" : "false", active ? "true" : "null");
    if (output_fd >= 0 && length > 0) (void)write(output_fd, buffer, length);
}
static void destroyed(gpointer data, GObject *object) {
    Context *context = data;
    g_hash_table_remove(contexts, object);
    publish("destroyed", context);
    g_free(context);
}
static gboolean observed(GSignalInvocationHint *hint, guint count,
                         const GValue *values, gpointer event) {
    (void)hint;
    if (count < 1) return TRUE;
    GObject *object = g_value_get_object(&values[0]);
    Context *context = g_hash_table_lookup(contexts, object);
    if (!context) {
        context = g_new0(Context, 1);
        context->generation = ++next_generation;
        g_hash_table_insert(contexts, object, context);
        g_object_weak_ref(object, destroyed, context);
    }
    if (g_str_equal(event, "start")) { context->known = TRUE; context->active = TRUE; }
    if (g_str_equal(event, "end")) { context->known = TRUE; context->active = FALSE; }
    publish(event, context);
    return TRUE;
}
G_MODULE_EXPORT void gtk_module_init(gint *argc, gchar ***argv) {
    (void)argc; (void)argv;
    if (contexts) return;
    const char *fd = g_getenv("LUDA_IME_PROBE_FD");
    if (!fd) return;
    output_fd = atoi(fd); /* Trusted fixture supplies already-open owned descriptor. */
    contexts = g_hash_table_new(g_direct_hash, g_direct_equal);
    gpointer klass = g_type_class_ref(GTK_TYPE_IM_CONTEXT);
    const char *signals[] = {"preedit-start", "preedit-end", "preedit-changed"};
    const char *events[] = {"start", "end", "changed"};
    for (guint i = 0; i < G_N_ELEMENTS(signals); i++) {
        guint id = g_signal_lookup(signals[i], GTK_TYPE_IM_CONTEXT);
        GSignalQuery query; g_signal_query(id, &query);
        if (!id || (query.signal_flags & G_SIGNAL_NO_HOOKS) ||
            !g_signal_add_emission_hook(id, 0, observed, (gpointer)events[i], NULL))
            g_error("Required public IM context signal hook unavailable");
    }
    g_type_class_unref(klass);
    publish("attached", NULL);
}
