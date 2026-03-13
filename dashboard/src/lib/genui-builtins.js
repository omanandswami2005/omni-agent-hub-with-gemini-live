/**
 * GenUI Built-in Components — Registers all default GenUI components.
 *
 * Import this file once at app startup (e.g. in main.jsx) to make all
 * built-in components available to the GenUIRenderer.
 *
 * To add a new component:
 * 1. Create your component in dashboard/src/components/genui/YourComponent.jsx
 * 2. Add a registerGenUI() call below with type, name, schema, and lazy import
 * 3. That's it — the GenUIRenderer will pick it up automatically
 */

import { registerGenUI } from '@/lib/genui-registry';

// ── Charts ─────────────────────────────────────────────────────────
registerGenUI({
    type: 'chart',
    name: 'DynamicChart',
    description: 'Renders line, bar, area, or pie charts from data arrays',
    schema: {
        chartType: { type: 'string', description: 'One of: line, bar, area, pie' },
        data: { type: 'array', required: true, description: 'Array of data objects' },
        config: { type: 'object', description: '{ title?, xKey?, yKeys? }' },
    },
    component: () => import('@/components/genui/DynamicChart'),
});

// ── Tables ─────────────────────────────────────────────────────────
registerGenUI({
    type: 'table',
    name: 'DataTable',
    description: 'Displays tabular data with column headers and rows',
    schema: {
        columns: { type: 'array', required: true, description: 'Column header strings' },
        rows: { type: 'array', required: true, description: 'Array of row objects keyed by column name' },
        title: { type: 'string', description: 'Optional table title' },
    },
    component: () => import('@/components/genui/DataTable'),
});

// ── Cards ──────────────────────────────────────────────────────────
registerGenUI({
    type: 'card',
    name: 'InfoCard',
    description: 'Rich information card with icon, title, description, and optional children',
    schema: {
        title: { type: 'string', required: true, description: 'Card title' },
        description: { type: 'string', description: 'Card description text' },
        icon: { type: 'string', description: 'Emoji or icon string' },
    },
    component: () => import('@/components/genui/InfoCard'),
});

// ── Code ───────────────────────────────────────────────────────────
registerGenUI({
    type: 'code',
    name: 'CodeBlock',
    description: 'Displays code with syntax info and copy button',
    schema: {
        code: { type: 'string', required: true, description: 'The code content' },
        language: { type: 'string', description: 'Programming language identifier' },
        filename: { type: 'string', description: 'Optional filename to display' },
    },
    component: () => import('@/components/genui/CodeBlock'),
});

// ── Images ─────────────────────────────────────────────────────────
registerGenUI({
    type: 'image',
    name: 'ImageGallery',
    description: 'Displays a grid of images with optional caption',
    schema: {
        images: { type: 'array', required: true, description: 'Array of image objects with url and optional alt' },
        caption: { type: 'string', description: 'Caption text below the gallery' },
    },
    component: () => import('@/components/genui/ImageGallery'),
});

// ── Timeline ───────────────────────────────────────────────────────
registerGenUI({
    type: 'timeline',
    name: 'TimelineView',
    description: 'Vertical timeline for events or history',
    schema: {
        events: { type: 'array', required: true, description: 'Array of { title, time, description? }' },
    },
    component: () => import('@/components/genui/TimelineView'),
});

// ── Markdown ───────────────────────────────────────────────────────
registerGenUI({
    type: 'markdown',
    name: 'MarkdownRenderer',
    description: 'Renders markdown content with GFM support and code highlighting',
    schema: {
        content: { type: 'string', required: true, description: 'Markdown text to render' },
    },
    component: () => import('@/components/genui/MarkdownRenderer'),
});

// ── Diff ───────────────────────────────────────────────────────────
registerGenUI({
    type: 'diff',
    name: 'DiffViewer',
    description: 'Side-by-side diff comparison of two text blocks',
    schema: {
        before: { type: 'string', required: true, description: 'Original text' },
        after: { type: 'string', required: true, description: 'Modified text' },
        language: { type: 'string', description: 'Language identifier for syntax' },
    },
    component: () => import('@/components/genui/DiffViewer'),
});

// ── Weather ────────────────────────────────────────────────────────
registerGenUI({
    type: 'weather',
    name: 'WeatherWidget',
    description: 'Displays weather information for a location',
    schema: {
        location: { type: 'string', required: true, description: 'City or place name' },
        temp: { type: 'number', required: true, description: 'Temperature value' },
        condition: { type: 'string', description: 'Weather condition text' },
        icon: { type: 'string', description: 'Emoji icon for the weather' },
    },
    component: () => import('@/components/genui/WeatherWidget'),
});

// ── Map ────────────────────────────────────────────────────────────
registerGenUI({
    type: 'map',
    name: 'MapView',
    description: 'Displays a Google Maps embed for a location',
    schema: {
        lat: { type: 'number', description: 'Center latitude' },
        lng: { type: 'number', description: 'Center longitude' },
        zoom: { type: 'number', description: 'Zoom level (default 13)' },
        markers: { type: 'array', description: 'Array of { lat, lng } marker objects' },
    },
    component: () => import('@/components/genui/MapView'),
});
