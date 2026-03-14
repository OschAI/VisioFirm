import { classColors } from './globals.js';

const DEFAULT_STYLE_CONFIG = {
    version: 1,
    defaults: {
        render_mode: 'outline_fill',
        stroke_width: 2,
        fill_opacity: 0.16,
        dash: [],
    },
    selected: {
        stroke_color: '#2563eb',
        stroke_width: 3,
    },
    preannotation: {
        fill_opacity: 0.08,
        dash: [10, 10],
    },
    classes: {},
};

let currentStyleConfig = structuredCloneSafe(DEFAULT_STYLE_CONFIG);

function structuredCloneSafe(value) {
    return typeof structuredClone === 'function'
        ? structuredClone(value)
        : JSON.parse(JSON.stringify(value));
}

function clampNumber(value, fallback, min, max) {
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return Math.min(max, Math.max(min, num));
}

function normalizeDash(value) {
    if (!Array.isArray(value)) return [];
    return value
        .map(part => Number(part))
        .filter(part => Number.isFinite(part) && part >= 0);
}

function normalizeHex(color, fallback = '#22c55e') {
    if (typeof color !== 'string') return fallback;
    const trimmed = color.trim();
    if (/^#[0-9a-fA-F]{6}$/.test(trimmed)) return trimmed;
    if (/^#[0-9a-fA-F]{8}$/.test(trimmed)) return trimmed.slice(0, 7);
    if (/^#[0-9a-fA-F]{3}$/.test(trimmed)) {
        return `#${trimmed[1]}${trimmed[1]}${trimmed[2]}${trimmed[2]}${trimmed[3]}${trimmed[3]}`;
    }
    return fallback;
}

function normalizeClassStyle(style, fallbackColor) {
    const safeStyle = style && typeof style === 'object' ? style : {};
    return {
        stroke_color: normalizeHex(safeStyle.stroke_color, fallbackColor),
        fill_color: normalizeHex(safeStyle.fill_color, fallbackColor),
        stroke_width: clampNumber(safeStyle.stroke_width, 2, 1, 24),
        fill_opacity: clampNumber(safeStyle.fill_opacity, 0.16, 0, 1),
        render_mode: ['outline', 'fill', 'outline_fill'].includes(safeStyle.render_mode)
            ? safeStyle.render_mode
            : 'outline_fill',
        dash: normalizeDash(safeStyle.dash),
    };
}

function hexToRgba(hex, opacity) {
    const safeHex = normalizeHex(hex);
    const r = parseInt(safeHex.slice(1, 3), 16);
    const g = parseInt(safeHex.slice(3, 5), 16);
    const b = parseInt(safeHex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

export function getDefaultStyleConfig() {
    return structuredCloneSafe(DEFAULT_STYLE_CONFIG);
}

export function normalizeStyleConfig(rawConfig, classes = []) {
    const config = rawConfig && typeof rawConfig === 'object' ? rawConfig : {};
    const defaults = config.defaults && typeof config.defaults === 'object' ? config.defaults : {};
    const selected = config.selected && typeof config.selected === 'object' ? config.selected : {};
    const preannotation = config.preannotation && typeof config.preannotation === 'object' ? config.preannotation : {};
    const classOverrides = config.classes && typeof config.classes === 'object' ? config.classes : {};

    const normalized = {
        version: 1,
        defaults: {
            render_mode: ['outline', 'fill', 'outline_fill'].includes(defaults.render_mode)
                ? defaults.render_mode
                : DEFAULT_STYLE_CONFIG.defaults.render_mode,
            stroke_width: clampNumber(defaults.stroke_width, DEFAULT_STYLE_CONFIG.defaults.stroke_width, 1, 24),
            fill_opacity: clampNumber(defaults.fill_opacity, DEFAULT_STYLE_CONFIG.defaults.fill_opacity, 0, 1),
            dash: normalizeDash(defaults.dash),
        },
        selected: {
            stroke_color: normalizeHex(selected.stroke_color, DEFAULT_STYLE_CONFIG.selected.stroke_color),
            stroke_width: clampNumber(selected.stroke_width, DEFAULT_STYLE_CONFIG.selected.stroke_width, 1, 24),
        },
        preannotation: {
            fill_opacity: clampNumber(preannotation.fill_opacity, DEFAULT_STYLE_CONFIG.preannotation.fill_opacity, 0, 1),
            dash: normalizeDash(Array.isArray(preannotation.dash) && preannotation.dash.length
                ? preannotation.dash
                : DEFAULT_STYLE_CONFIG.preannotation.dash),
        },
        classes: {},
    };

    classes.forEach(cls => {
        const fallbackColor = normalizeHex(classColors[cls], '#22c55e');
        normalized.classes[cls] = normalizeClassStyle(classOverrides[cls], fallbackColor);
    });

    return normalized;
}

export function setCurrentStyleConfig(styleConfig, classes = []) {
    currentStyleConfig = normalizeStyleConfig(styleConfig, classes);
}

export function getCurrentStyleConfig() {
    return structuredCloneSafe(currentStyleConfig);
}

export function getResolvedClassStyle(className) {
    const fallbackColor = normalizeHex(classColors[className], '#22c55e');
    const defaults = currentStyleConfig.defaults;
    const override = currentStyleConfig.classes[className] || {};
    return {
        renderMode: override.render_mode || defaults.render_mode,
        strokeWidth: override.stroke_width ?? defaults.stroke_width,
        fillOpacity: override.fill_opacity ?? defaults.fill_opacity,
        dash: override.dash ?? defaults.dash,
        strokeColor: normalizeHex(override.stroke_color || fallbackColor, fallbackColor),
        fillColor: normalizeHex(override.fill_color || fallbackColor, fallbackColor),
    };
}

export function getResolvedAnnotationStyle(annotation, { selected = false } = {}) {
    const base = getResolvedClassStyle(annotation.label || '');
    const isPreannotation = Boolean(annotation.isPreannotation);
    const strokeColor = base.strokeColor;
    const strokeWidth = selected
        ? currentStyleConfig.selected.stroke_width
        : base.strokeWidth;
    const fillOpacity = isPreannotation
        ? currentStyleConfig.preannotation.fill_opacity
        : base.fillOpacity;
    const dash = isPreannotation
        ? currentStyleConfig.preannotation.dash
        : base.dash;

    return {
        renderMode: base.renderMode,
        strokeColor,
        strokeWidth,
        dash,
        fillColor: hexToRgba(base.fillColor, fillOpacity),
    };
}
