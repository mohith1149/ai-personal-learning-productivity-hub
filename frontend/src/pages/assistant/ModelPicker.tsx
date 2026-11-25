import { useEffect } from "react";
import { setModelChoice, useAiStatus, useModelChoice, useModels } from "../../api/assistant";
import { controlClass } from "../../components/forms";
import { cx } from "../../components/ui";

/** Switch between providers (those with a key in backend/.env) and between each one's models. The pick is remembered in this browser. */
export function ModelPicker({ className }: { className?: string }) {
  const models = useModels();
  const status = useAiStatus();
  const choice = useModelChoice();
  const providers = models.data?.providers ?? [];

  // A remembered pick for a provider that no longer has a key is dropped, so requests fall back to the default instead of failing.
  useEffect(() => {
    if (models.data && choice && !providers.some((p) => p.provider === choice.provider)) setModelChoice(null);
  }, [models.data, choice, providers]);

  if (providers.length === 0) return null;
  const fallback = providers.find((p) => p.provider === models.data?.default_provider) ?? providers[0];
  const value = choice && providers.some((p) => p.provider === choice.provider) ? `${choice.provider}|${choice.model}` : `${fallback.provider}|${status.data?.model ?? fallback.default_model}`;
  const known = providers.some((p) => p.models.some((m) => `${p.provider}|${m}` === value));

  return (
    <select
      aria-label="Model"
      title="Which AI model answers. Providers and models come from your backend/.env keys."
      value={value}
      onChange={(e) => {
        const [provider, ...rest] = e.target.value.split("|");
        setModelChoice({ provider, model: rest.join("|") });
      }}
      className={cx(controlClass, "max-w-full py-1.5 text-xs", className)}
    >
      {!known && <option value={value}>{value.split("|")[1]}</option>}
      {providers.map((p) => (
        <optgroup key={p.provider} label={p.label}>
          {p.models.map((m) => (
            <option key={m} value={`${p.provider}|${m}`}>
              {m}
              {m === p.default_model ? " (default)" : ""}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
