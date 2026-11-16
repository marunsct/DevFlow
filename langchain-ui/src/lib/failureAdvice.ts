/**
 * What a run's failure means for its owner, and what to do about it (LR.34).
 *
 * Found in the launch review: a failed run showed the harness's own reason ("The acceptance suite proves nothing
 * after 5 rounds: ...") and "Something went wrong", and nothing said whether to resume, rewind, clone or rewrite the
 * brief. The reason stays, under the advice.
 */
export type FailureAdvice = { kind: string; meaning: string; action: string };

const RULES: { test: RegExp; advice: FailureAdvice }[] = [
  {
    test: /model server|did not answer|connection (?:refused|error)|could not reach|timed out waiting for the model|no model loaded/i,
    advice: { kind: 'The model server', meaning: 'The model stopped answering, so the run could not go on.',
      action: 'Check the model server is running and loaded, then Resume: the run continues from its last completed stage.' },
  },
  {
    test: /spending ceiling|budget|max_run_(?:tokens|cost)|cost limit/i,
    advice: { kind: 'The budget', meaning: 'The run reached the token or cost ceiling set for it.',
      action: 'Raise MAX_RUN_TOKENS or MAX_RUN_COST_USD in the settings if the run is worth more, then Resume.' },
  },
  {
    test: /acceptance suite (?:proves nothing|cannot run|does not run)|suite.*could not (?:run|load)/i,
    advice: { kind: 'The acceptance tests', meaning: 'The tests written from the brief could not be made to run or to prove anything.',
      action: 'Rewind to the acceptance tests stage to have them written again; if it fails the same way, make the brief\'s Interface section more exact and Clone.' },
  },
  {
    test: /re-planned \d+ times|could not be accepted|revision limit/i,
    advice: { kind: 'A sprint that could not be finished', meaning: 'The same sprint was planned again several times and its tests still failed.',
      action: 'Read the defect report below, add a direction in a note, and Resume; or narrow the brief and Clone.' },
  },
  {
    test: /structured response|did not say what to change|returned no|without returning/i,
    advice: { kind: 'A model answer', meaning: 'A stage\'s model answered in a shape the harness could not use.',
      action: 'Resume: the stage runs again. If it fails twice, try Rewind to that stage, or a larger model.' },
  },
  {
    test: /time limit|soft time limit|segments/i,
    advice: { kind: 'Its time', meaning: 'The run used all the time it is given.',
      action: 'Resume to give it more time, or narrow the brief: a smaller product finishes sooner.' },
  },
];

const UNKNOWN: FailureAdvice = {
  kind: 'Something unexpected',
  meaning: 'The run stopped for a reason the page does not recognise.',
  action: 'Resume once: most stops are passing. If it stops again at the same place, read the reason below and Rewind or Clone.',
};

export function failureAdvice(error: string | null | undefined): FailureAdvice | null {
  if (!error) return null;
  return RULES.find((rule) => rule.test.test(error))?.advice ?? UNKNOWN;
}
