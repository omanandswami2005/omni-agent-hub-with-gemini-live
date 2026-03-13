/**
 * GenUI Component Registry — Pluggable architecture for generative UI.
 *
 * Any developer can register a new GenUI component by calling
 * `registerGenUI()` with a type key, prop schema, and lazy component.
 *
 * Forward-compatible with OpenUI: the schema structure maps directly
 * to OpenUI's `defineComponent({ name, props: z.object(...), component })`.
 * When migrating to OpenUI, each registry entry becomes a `defineComponent` call.
 *
 * @example
 * // Register a new component:
 * registerGenUI({
 *   type: 'weather',
 *   name: 'WeatherWidget',
 *   description: 'Displays weather information for a location',
 *   schema: {
 *     location: { type: 'string', required: true, description: 'City name' },
 *     temp:     { type: 'number', required: true, description: 'Temperature' },
 *     condition:{ type: 'string', description: 'Weather condition text' },
 *     icon:     { type: 'string', description: 'Emoji icon' },
 *   },
 *   component: () => import('@/components/genui/WeatherWidget'),
 * });
 */

const _registry = new Map();

/**
 * Register a GenUI component.
 *
 * @param {object} entry
 * @param {string} entry.type        - Unique type key (e.g. 'chart', 'table', 'weather')
 * @param {string} entry.name        - Human-readable component name
 * @param {string} [entry.description] - What this component does (used for prompt generation)
 * @param {object} [entry.schema]    - Prop schema: { propName: { type, required?, description? } }
 * @param {() => Promise} entry.component - Lazy import function: () => import('./MyComponent')
 */
export function registerGenUI(entry) {
    if (!entry.type || !entry.component) {
        throw new Error(`GenUI registration requires 'type' and 'component'. Got: ${JSON.stringify(entry)}`);
    }
    _registry.set(entry.type, entry);
}

/**
 * Get a registered GenUI component entry by type.
 * @param {string} type
 * @returns {object|undefined} The registry entry or undefined
 */
export function getGenUI(type) {
    return _registry.get(type);
}

/**
 * Get all registered GenUI entries.
 * @returns {Map<string, object>}
 */
export function getAllGenUI() {
    return new Map(_registry);
}

/**
 * Get all registered types.
 * @returns {string[]}
 */
export function getRegisteredTypes() {
    return [..._registry.keys()];
}

/**
 * Generate a prompt-friendly description of all registered GenUI components.
 * Useful for including in LLM system prompts so the model knows what UI
 * components it can emit.
 *
 * Forward-compatible with OpenUI's `library.prompt()`.
 *
 * @returns {string} A formatted string describing available components and their schemas
 */
export function generateGenUIPrompt() {
    const lines = ['Available GenUI components:\n'];
    for (const [type, entry] of _registry) {
        lines.push(`## ${entry.name || type}`);
        if (entry.description) lines.push(entry.description);
        lines.push(`Type key: "${type}"`);
        if (entry.schema) {
            lines.push('Props:');
            for (const [prop, spec] of Object.entries(entry.schema)) {
                const req = spec.required ? ' (required)' : '';
                const desc = spec.description ? ` — ${spec.description}` : '';
                lines.push(`  - ${prop}: ${spec.type || 'any'}${req}${desc}`);
            }
        }
        lines.push('');
    }
    return lines.join('\n');
}
