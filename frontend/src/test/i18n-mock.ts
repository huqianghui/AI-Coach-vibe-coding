import admin from "../../public/locales/en-US/admin.json";
import analytics from "../../public/locales/en-US/analytics.json";
import auth from "../../public/locales/en-US/auth.json";
import coach from "../../public/locales/en-US/coach.json";
import common from "../../public/locales/en-US/common.json";
import conference from "../../public/locales/en-US/conference.json";
import dashboard from "../../public/locales/en-US/dashboard.json";
import metaSkill from "../../public/locales/en-US/meta-skill.json";
import nav from "../../public/locales/en-US/nav.json";
import prompts from "../../public/locales/en-US/prompts.json";
import scoring from "../../public/locales/en-US/scoring.json";
import session from "../../public/locales/en-US/session.json";
import skill from "../../public/locales/en-US/skill.json";
import training from "../../public/locales/en-US/training.json";
import voice from "../../public/locales/en-US/voice.json";

const resources: Record<string, unknown> = {
  admin,
  analytics,
  auth,
  coach,
  common,
  conference,
  dashboard,
  "meta-skill": metaSkill,
  nav,
  prompts,
  scoring,
  session,
  skill,
  training,
  voice,
};

type TranslationOptions = Record<string, unknown> & { defaultValue?: string };

function lookup(resource: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((value, part) => {
    if (typeof value !== "object" || value === null || !(part in value)) {
      return undefined;
    }
    return (value as Record<string, unknown>)[part];
  }, resource);
}

function interpolate(value: string, options: TranslationOptions): string {
  return value.replace(/{{\s*([^},]+)(?:,[^}]*)?\s*}}/g, (_, name: string) => {
    const replacement = options[name.trim()];
    return replacement === undefined ? `{{${name.trim()}}}` : String(replacement);
  });
}

export function createTestTranslator(namespace?: string | string[]) {
  const defaultNamespaces = namespace
    ? Array.isArray(namespace)
      ? namespace
      : [namespace]
    : Object.keys(resources);

  return (key: string, options: TranslationOptions = {}): string => {
    const separator = key.indexOf(":");
    const explicitNamespace = separator >= 0 ? key.slice(0, separator) : undefined;
    const resourceKey = separator >= 0 ? key.slice(separator + 1) : key;
    const namespaces = explicitNamespace ? [explicitNamespace] : defaultNamespaces;

    for (const candidate of namespaces) {
      const value = lookup(resources[candidate], resourceKey);
      if (typeof value === "string") {
        return interpolate(value, options);
      }
    }

    return options.defaultValue ?? key;
  };
}
