import type { PermissionProfile } from "../state/types";

const PROFILES: readonly PermissionProfile[] = [
  "PROJECT_READ_ONLY",
  "ASK_ALWAYS",
  "RISK_BASED",
  "PROJECT_FULL_ACCESS",
  "CUSTOM",
];

export function PermissionProfileSelect({
  value,
  disabled,
  onChange,
}: {
  value: PermissionProfile;
  disabled: boolean;
  onChange: (value: PermissionProfile) => void;
}) {
  return (
    <label>
      Permission profile
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as PermissionProfile)}
      >
        {PROFILES.map((profile) => (
          <option key={profile} value={profile}>
            {profile}
          </option>
        ))}
      </select>
      {value === "PROJECT_FULL_ACCESS" ? (
        <span>Project capability only; this is not full computer access.</span>
      ) : null}
    </label>
  );
}
