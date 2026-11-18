import type { TourStep } from "@/components/ui/guided-tour";

/** Raise this when the tour changes enough that everyone should see it again. */
export const PLATFORM_TOUR_VERSION = 1;

type Options = { workspaceName: string; canSubmit: boolean; hasAdministration: boolean };

export function platformTourSteps({ workspaceName, canSubmit, hasAdministration }: Options): TourStep[] {
  const steps: (TourStep | false)[] = [
    {
      title: "Welcome to TRANSPIRE",
      body: <>
        <p>This is where {workspaceName} turns everyday improvement ideas into approved, tracked results.</p>
        <p>The next minute shows you where everything lives. You can replay it any time from your profile menu.</p>
      </>,
    },
    {
      title: "How an idea travels",
      body: <ul>
        <li><strong>Submit</strong>: describe the problem, the change and the value you expect.</li>
        <li><strong>Approve</strong>: it follows your workspace’s approval route, stage by stage.</li>
        <li><strong>Charter</strong>: an approved idea gets a project charter with owners and milestones.</li>
        <li><strong>Deliver</strong>: the project tracks milestones and the benefits it actually achieves.</li>
      </ul>,
    },
    {
      target: "nav-home",
      title: "Home is your starting point",
      body: <p>Drafts to continue, ideas returned for correction, your submitted ideas and anything waiting for your decision all appear here first.</p>,
    },
    canSubmit && {
      target: "nav-submit",
      title: "Every improvement starts here",
      body: <p>A guided four-step form helps you frame the idea, explain the case and estimate its value. Save a draft whenever you like and come back to it from Home.</p>,
    },
    {
      target: "nav-ideas",
      title: "Learn from the Idea Bank",
      body: <p>Browse ideas from across the workspace, see where each one is in its journey, and ask to join an idea you can help with. Checking here first avoids duplicate submissions.</p>,
    },
    {
      target: "nav-projects",
      title: "Approved ideas become projects",
      body: <p>Follow each project’s charter, milestones and the monthly benefits it delivers against the original estimate.</p>,
    },
    {
      target: "nav-inbox",
      title: "Your Inbox keeps you moving",
      body: <p>Approvals assigned to you, correction requests and updates on your ideas land here. The badge shows how many need your action.</p>,
    },
    hasAdministration && {
      target: "nav-admin",
      title: "Administration",
      body: <p>Because you manage this workspace, you can set up people, catalogues, approval workflows and reminders here.</p>,
    },
    {
      target: "account",
      title: "Your profile and this tour",
      body: <p>Edit your profile, review your activity, switch organisation or theme. Choose <strong>Take the tour</strong> here whenever you want a refresher.</p>,
    },
  ];
  return steps.filter((step): step is TourStep => Boolean(step));
}
