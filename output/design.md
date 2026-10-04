# Campus Customs Desk: dashboard design

The board in `frontend/` (React + Vite + TypeScript) is where one person watches five AI agents run a small shop and holds the only checkbook. Every design choice serves two jobs: **make the agents easy to follow** and **make the money moments impossible to miss.**

Run it with `npm run dev` in `frontend/`, which opens `http://localhost:5173`. The board talks to the FastAPI backend at `VITE_API_BASE` (`frontend/.env`, default `http://localhost:8000`).

## Look and feel

- **Yale Blue and white.** White cards on a cool off-white canvas (`#f4f6fa`), with **Yale Blue** (`#00356B`) as the one "this matters" color: selected ticket, approval card, money leaving. Yale's medium blue (`#286DC0`) is used only in gradients and highlights. Soft navy-tinted shadows lift the cards. Blue is never decoration. If something is Yale Blue, it's either yours to act on or it's money. A light theme also reads better on laptops in bright rooms and feels at home for a Yale shop.
- **Distinctive font pairing, one job per typeface:**
  - **Fraunces** (variable serif, with its `SOFT` and `WONK` axes turned up) for the title, ticket numbers, and every dollar amount. It gives the desk a warm, editorial, slightly hand-set feel, like a shop ledger rather than a SaaS admin panel. The italic, wonky ticket numbers (*101*, *102*, *103*) read like a shopkeeper's handwriting.
  - **Space Grotesk** for interface text: clean and a little quirky, so labels stay crisp next to the serif.
  - **JetBrains Mono** for anything machine-made: tool calls, SKUs, run stats. When something is monospace, a tool did it.
  - All three are bundled with `@fontsource`, so the board looks the same offline.
- **Subtle motion with meaning.** New feed items rise in (8px fade, 420ms). Ticket cards slide slightly on hover. A blue sweep runs under the ticket being worked. Nothing loops unless something is actually happening, and `prefers-reduced-motion` turns all of it off.

## Layout

A three-column desk, read left to right like the work itself:

| Left: *what's on the desk* | Center: *the stage* | Right: *what needs you* |
|---|---|---|
| Ticket cards (101/102/103) with status and **Run team ▸** | Selected ticket header, the five-agent roster, and the live conversation feed | Approval cards, then "What each agent did" |
| Checking balance and ledger | | |

**Sized for laptops.** On screens 1201px and wider, the board is a one-screen dashboard. The three columns fill exactly the window height, with the stage's feed and the side columns scrolling inside themselves, so the balance, the tickets and the approval card are always visible without scrolling the page. On a wide monitor the board is capped at 1480px and centered instead of stretching. I checked 1366×768 (no page scroll, no clipped labels) and 1920×1080 (centered, 296 / 818 / 346px columns). At 1500px and below the side columns slim to 260 / 300px. On short screens (≤820px tall) the top bar and ticket cards tighten. Below 1200px the right column drops under the stage, and on small screens everything stacks into one column. While the backend is unreachable, the tickets show shimmering placeholders and the stage shows the command to start the server, instead of empty boxes.

## How the agents read differently

Each agent has its own **color, line icon, role label, and live status**, and those stay the same everywhere: roster card, feed avatar, chat bubble tint, tool-chip border, summary card stripe, and "Requested by" on approvals. You can follow one agent through the whole run by color alone.

| Agent | Color | Icon | Role label |
|---|---|---|---|
| The Boss | Yale Blue `#00356B` | crown | Runs the board |
| Inventory | teal `#0E9F8E` | box | Stock & vendors |
| Accounting | amber `#C98700` | coin stack | Cash & pricing |
| Facilities | violet `#7357E0` | storefront | Lease & rent |
| Customer Service | coral `#E2583A` | speech bubble | Customer replies |

The Boss shares Yale Blue on purpose: it *is* the desk's voice. The four specialists spread around the color wheel, deep enough to stay readable on white, so no two are confused at a glance. Each roster card stacks an avatar and a status pill over the full name and role label, so nothing is cut off on a 1366px laptop.

**Live status** comes from replaying the audit-trail events (`GET /api/events`, polled every 1.2 s during a run):
- **Idle**: dimmed card. The agent wasn't needed, which is itself information: ticket 102 should light up only the Boss and Facilities.
- **Thinking**: a breathing ring around the avatar, and the detail line reads "reading tool results".
- **Using tool**: a dashed ring that slowly spins, and the detail line names the tool (`get_rent_due`, `delegate → Facilities`).
- **Done**: a calm ring and a green dot. **Error**: a red ring.

**The feed is a group chat, not a log.**
- **Speech is chat bubbles**, tinted in the speaker's color with a "tail" corner. A delegation renders as "The Boss → Facilities" followed by the exact task the Boss wrote. That makes the handoffs, the most interesting part of a multi-agent system, readable as conversation.
- **Tool calls are monospace chips** (`request_payment(kind=rent, ref_id=1, amount=2400)`), bordered in the agent's color. Hover a chip for the full arguments. Results come back as quieter chips (`✓ get_rent_due`). A refusal turns red with the reason, so a guardrail firing is visible (`✗ create_purchase_order: Refused: Bulldog Print Co has open invoice 501`).
- **Reports** close each agent's turn as a bubble with a colored left rule.
- Run dividers mark start and finish, and three bouncing blue dots show the team is still working. The feed auto-scrolls unless you've scrolled up to read.

## How money shows up

- **The approval card is the loudest thing on the page, on purpose.** It's the one moment the human has to act. It has a Yale Blue gradient border that softly pulses, a "YOUR APPROVAL NEEDED" flag, the **amount in big Fraunces**, the payee, the agent's reason, who asked (in that agent's color), and a preview of **"Checking after: $X"**. If paying would overdraw the account, the card says so and Approve is disabled. The Approve button is solid Yale Blue with the amount on it ("Approve $2,400"), so you always know what you're signing. Approvals lock while a run is in progress, so the cash can't change under an agent mid-decision.
- **"Approving as" in the header.** Every payment is signed by a named human, and the backend refuses agent names.
- **The balance is a big Fraunces number that counts down.** After an approved payment it ticks from $3,400.00 to $1,000.00 over about 1.4 s, briefly flushes blue, and a `−$2,400` floats up and fades. You *feel* money leave the account. Underneath, two small tiles show **pending approvals** and **what's left if everything pending is approved**, the number the Boss plans around.
- **The ledger is grouped per ticket**: each paid request under "Ticket 102" / "Ticket 101", with payee, who approved it, and when. It answers "where did the money go, and who said yes?" at a glance.

## How resolved tickets show up

- Each ticket card carries a status pill: Open, In progress, **Needs approval** (solid Yale Blue), Waiting on vendor, or Resolved. Once every approval on a ticket is decided, the pill switches to a dashed-green **Ready to close**, so a ticket never still says "Needs approval" after you've paid.
- When a ticket is resolved, either by the Boss at the end of a run or by a human clicking **Mark resolved ✓** (refused while approvals are pending), a green **RESOLVED** rubber stamp slams onto the card: it scales down from 2.2× with a little overshoot, tilted −11°, and the card dims. It's a small, physical, satisfying "done", like stamping a paper ticket at a real counter.

## Summaries

"What each agent did" shows one card per agent that worked the ticket, specialists first and the Boss last as the wrap-up. Each card has the agent's one-line summary, up to four concrete actions (request IDs, quote IDs, draft IDs), and a blue **Needs you** line, so the human can audit the run in ten seconds without reading the whole feed. Run stats (delegations, model calls, tokens) sit under the roster in mono, for anyone watching cost.

## Why it should be enjoyable to use

- **It feels like watching a small team, not reading logs.** The colors, avatars and chat bubbles let you watch the Boss hand rent to Facilities and see Facilities quietly do its three tool calls.
- **Your role is clear and important.** Agents only ask, and you decide. The page pulls your eye to exactly the cards that need you and makes the click feel weighty: big amount, preview of the balance after, a stamp and a countdown in return.
- **Restraint.** One accent color, three fonts with clear jobs, and motion only when something changes. The page stays calm while agents are idle and comes alive while they work.
- **Honest.** Refusals and guardrails aren't hidden. Red chips show where the rules stopped an agent, which builds trust that the system won't overspend.
