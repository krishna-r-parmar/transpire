import type { TourStep } from "@/components/ui/guided-tour";

/** Raise this when the guide changes enough that everyone should see it again. */
export const SUBMIT_IDEA_TOUR_VERSION = 1;

export const submitIdeaTourSteps: TourStep[] = [
  {
    title: "How to submit a strong idea",
    body: <>
      <p>Reviewers decide on what you write here, so a clear, evidenced idea moves faster.</p>
      <p>This guide walks through each part of the form. Nothing you have typed is changed.</p>
    </>,
  },
  {
    target: "submit-steps",
    title: "Four short stages",
    body: <p>You frame the idea, explain the case, estimate its value, then review the approval route before submitting. Your progress is shown here the whole way.</p>,
  },
  {
    target: "submit-context",
    title: "Where it happens",
    body: <p>Your name and workspace are attached for you. If sites and departments are set up, choose where the problem actually occurs so the right people review it.</p>,
  },
  {
    target: "submit-type",
    title: "Kaizen or Project?",
    body: <ul>
      <li><strong>Kaizen</strong>: a focused change you can usually test and adopt within the existing process.</li>
      <li><strong>Project</strong>: needs coordinated delivery, formal analysis, investment or several teams.</li>
      <li>Pick by the shape of the work, not how important it feels.</li>
    </ul>,
  },
  {
    target: "submit-classification",
    title: "Category unlocks guidance",
    body: <p>Choosing a category and subcategory fills in starter prompts: a title structure, the typical problem, business-case direction and a suggested KPI. Treat them as a starting point and replace them with your own facts.</p>,
  },
  {
    target: "submit-step-2",
    title: "Idea details: tell the story",
    body: <ul>
      <li>A one-line title naming the process and the improvement.</li>
      <li>The problem as it is today. Use What, When, Where, Who, Which and How so someone else could verify it.</li>
      <li>The business case, plus the baseline and target with units, e.g. 25 → 10 min.</li>
    </ul>,
  },
  {
    target: "submit-step-3",
    title: "Impact: show the value",
    body: <ul>
      <li>Pick every SQDCP area it improves: Safety, Quality, Delivery, Cost, Productivity.</li>
      <li>Estimate annual saving, cost avoidance and investment in ₹. TRANSPIRE works out the payback and the USD equivalent.</li>
      <li>Rough, honest numbers beat none at all.</li>
    </ul>,
  },
  {
    target: "submit-step-4",
    title: "Review and submit",
    body: <p>Check every section, then see the exact approval route your idea will follow: each stage, who approves it and its target time. Submit when it reads well to someone outside your team.</p>,
  },
  {
    target: "submit-save",
    title: "Save as you go",
    body: <p>Save a draft at any point and pick it up later from Home. Once a draft is saved it gets a reference number.</p>,
  },
  {
    title: "After you submit",
    body: <>
      <p>Follow your idea’s progress from Home and your Inbox. If an approver needs more detail, it comes back to you as a correction and you resubmit with the history kept.</p>
      <p>Once it is approved, you will complete a project charter so delivery can begin. Replay this guide any time with <strong>How to submit</strong>.</p>
    </>,
  },
];
