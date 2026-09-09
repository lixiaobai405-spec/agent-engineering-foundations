import type { ConversationPlanState } from "../state/types";

export function PlanPanel({
  plan,
}: {
  plan: ConversationPlanState | null;
}) {
  if (plan === null) {
    return null;
  }
  return (
    <section className="chat-plan-panel" aria-label="Execution plan">
      <h2>Execution plan</h2>
      <p className="chat-plan-panel__goal">{plan.goal}</p>
      <ol>
        {plan.steps.map((step) => (
          <li key={step.step_id}>
            <strong>{step.status}</strong> {step.description}
          </li>
        ))}
      </ol>
    </section>
  );
}
