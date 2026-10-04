# AI Prompt Log

This file records the prompts and follow-ups used while building HW5 (Campus Customs Multi-Agent Operations).

## Problem 1: Vibe coder prompts

### Original prompt

ok today we are going to work on hw 5. campus customs multi-agent operations is the agentic team that runs the shop - open tickets (customer orders, rent, unpaid bills, discount requests) land on a board. we will build an MCP server, a FastAPI backend with a multi-agent team (Boss, Inventory, Accounting, Facilities, Customer Service, any agent can delegate to any other), and a React dashboard so a human can watch the agents and approve requests. unzip data.zip so we have data/campus_customs.db, then make a copy called data/campus_customs_new.db and point the MCP server and backend at that working copy - keep the original untouched so we can reset. review the shop rules (desk.date_today is today, vendor lead times from vendors table, vendors wont ship with an open unpaid invoice, human approval for every payment, pay tool must refuse negative balances, no emailing customers or calling vendors) and we will get started shortly.

### Follow-up prompts

use gpt-6-luna through portkey for this homework for every agent/code/run.

Then: create AI_prompts.md and keep it updated as always - one section for each problem, with the problem number and title, the prompt in my own words, one follow-up prompt if needed, and one sentence on what was lacking after the first prompt.

### What was lacking after the first prompt

The first prompt didn't say which model to use, and the root AGENTS.md (gpt-5.6-luna) conflicted with the assignment (gpt-6-luna), so the model had to be confirmed.

## Problem 2: Study the Campus Customs database

### Original prompt

ok problem 2: study the campus customs database. open data/campus_customs.db and look through every table and field. copy the original file to data/campus_customs_new.db - later problems will update that working copy. study the 3 open tickets so you see how they link to other tables. start output/harness.md. for each table, list the fields and one short line on why the table matters for the agents. keep growing the harness file in later problems.

### Follow-up prompts

None yet.

### What was lacking after the first prompt

Nothing yet.

## Problem 3: Build the MCP server

### Original prompt

ok problem 3: build the MCP server. write an MCP server in mcp_server/ using FastMCP that talks to data/campus_customs_new.db - no need to connect or run it in this problem. every agent will use these tools, and we will add more later - for now write 3 tools I know I'll need for the tickets in the database. keep names clear and never invent data, only use what's in the db. in output/harness.md list each of the 3 tools with which table it reads, which ticket it unlocks (101, 102, 103), and one sentence on why it's the right tool for that ticket - tie it to the ticket, not vague lines like "reads inventory". also add a short mcp_server/README.md explaining what the server is for, which database file it uses, and its 3 tools.

### Follow-up prompts

None yet.

### What was lacking after the first prompt

Nothing yet.

## Problem 4: Add the MCP server to the vibe coder and test each tool

### Original prompt

ok problem 4: add the mcp server to the vibe coder and test each tool. add the mcp server to this project so you can call its tools, and save the connection JSON in .mcp.json at the project root (or however local MCP server lists are saved). then test each of the 3 tools and save the evidence in output/mcp_smoke.json. for every tool include the prompt asked to the vibe coder, the tool name, and the tool output, which must match the values in data/campus_customs_new.db: check_stock on tickets 101 and 103 to see if the items are in stock, get_vendor_status on tickets 101 and 103 to see if it gets the vendor status right, and get_rent_due on ticket 102 to see how much rent is due.

### Follow-up prompts

we will continue working on hw5 here since you asked me to open a new session. re-run the problem 4 smoke tests with the MCP tools - does it work here?

### What was lacking after the first prompt

The first session could only test the server from a script, because the newly added MCP server's tools don't load until a new session starts, so the live tool calls had to be re-run in a fresh session.

## Problem 5: Build the agent team and grow the MCP tools

### Original prompt

now lets work on problem 5: build the agent team and grow the mcp tools. build the agentic team for cc using pydnaticai: boss, inventory, accounting, facilities, and customer service. include prompts, models, agent loops so they can delegate work to each other with full connectivity. put the agent prompts in backend/prompts/ - one file per agent. put data types in backend/models.py and the agent files under backend/ . use PORTKEY_API_KEY and only gpt 6 luna for every agent as mentioned earlier. write each prompt in own works with shop rules that agent needs. more detailed prompts that cover all aspects of an agents work and scope are needed here. add any tools the agents need to the mcp server so they can work on open tikcets. shop facts come from mcp server over data/campus_customs_new.db. dont invent a second shop tools layer that bypasses mcp. wire agents so they append to output/audit_trail.json as they run; for each agent loop step record enough to audit later. append to this file dont wipe each run. in output/harness.md list each agent and each mcp tool including ones added in this problme along with which table the tool uses. also add a short safety section: the gaurdrails a real business would want when agents touch real customers and real money, plus limits that keep token use in check. now update mcp_server/README.md so the tool list matches what we have now

### Follow-up prompts

None yet.

### What was lacking after the first prompt

The prompt didn't set a time limit per model call, so the first test run stalled on a hung gpt-6-luna request until a per-call timeout and a run wall-clock limit were added.

## Problem 6: Plan the 3 tickets

### Original prompt

now lets work on problem 6: plan the 3 tickets. before you write the backend, we will write what we expect the team to do on each open ticket.ok here is my expection: for ticket 101 the boss will ask inventory to check stock for order, then inventory will say out of stock. then accounting will tell us about the dues to the vendor and will pay off the dues after asking for human approve. through all this customer service will tell tauhid about the delay and when it can be expected back in stock. once paid then inventory will update it to say back in stock and customer service will help complete order. for 102: boss will ask accounting or facilities to deal with rent due - they will pay after checking w boss and human. for 103: boss will tell inventory, accounting, customer services to work together. inventory will tell us we are 12 short and accounting will tell us how much disount can be given and will help with vendor payment. throughout this cusomter service will help deal with customer. now build output/desk_tickets.html - a page tha twe can double click with one tab per ticket (101,102,103). also add empty cash and reflection tabs for later problems (leave blank for now). on each ticket tab, fill an expected section only (later we will fill an actual section after u run the agents). for each tickets expected section, write - who the boss should call first and why, all the agent delegations you expect - not "boss calls everyone", and which mcp tools you expect that run to use. do this based on the expectations i laid out earlier. plans that send every specialist on every ticket score low - we will compare this plan to what actually happens when the agents resolve the three tickets.

### Follow-up prompts

None yet.

### What was lacking after the first prompt

The prompt said "accounting or facilities" for rent and expected agents to "pay" and mark items "back in stock", so the plan had to pick one owner (Facilities) and explain that agents only request payments and that no tool yet receives stock when a shipment arrives.

## Problem 7: Backend routes

### Original prompt

now we will work on problem 7: backend routes. your react frontend dashboard in next problem needs a backend it can call. in backend/main.py, use fastapi and add routes that do the following: Return the three tickets and whether each is open or resolved. Take a ticket id and run your agent team on that ticket. Return recent agent events — what each agent said and which tools they used — so the board can refresh. Approve a payment or purchase after a human clicks approve (agents only prepare the pay; this route is what actually changes cash). Return the current checking balance from cash_accounts. Reset the database to the original values when you want to try a fresh run. from the backend/ folder, start the server with: uvicorn main:app --reload --port 8000. this turns on your backend at https://localhost:8000 so the frontend dashboard can call those routes. in output/harness.md, list each route in one line (what url/what it does)

### Follow-up prompts

None yet.

### What was lacking after the first prompt

The prompt didn't say how to return a team run that takes several minutes, so the run route starts it in the background and returns a run_id the board polls (and the server is plain http://localhost:8000, not https).

## Problem 8: Frontend dashboard

### Original prompt

now problem 8: build frontend dashboard in frontend/ with react+vite+ typescript. the page should call the routes built in problem 7. at minimum the board should: List all three tickets. Let you pick one ticket and start the agent team on it. Show each agent and what they are saying / doing while the ticket runs. Mark a ticket resolved when the run finishes. Show a short summary of what each agent did on that ticket. Let a human approve a pay or purchase when asked. Show the checking balance (it should drop after an approved pay). make dashboard look good. each of the five agent gets its own color, icon, role label, and live status (idle / thinking / using tool / done). Speech shows as chat bubbles; tool calls show as monospace chips. large animated balance that ticks down after an approved pay, plus a small ledger of changes per ticket. a bold, attention-grabbing card with amount, reason, and Approve/Reject button. also make sure to have distinctive font pairing, subtle motion on new events. tell the front end to talk to your backend at https://localhost:8000. on the backend allow the vite page origin (usually https://localhost:5173) so the browser is allowed to call these routes. start the board with npm run dev. this opens the react desk in browser so i can pick tickets and watch agents. write output/design.md with what you chose for the dashboard look (layout, how agents read differently, how resolved tickets and cash show up) and why - including the creative choices that make it feel special and something humans would enjoy using.

### Follow-up prompts

can you make it blue and white theme instead of black pink - also make sure its dimensions are ok according to laptop (ya and this should be the yale blue)

## Problem 9: Resolve the tickets

### Original prompt

problem 9 now: resolve the tickets. before testing the agents on a full run over the 3 tickets, reset the working database data/campus_customs_new.db again so you can start clean. note the starting checking balance. then run all 3 tickets on the board until each is resolved. open output/desk_tickets.html from problem 6. on each ticket tab, fill the actual section from this run: which agents worked, what they delegated, and which tools they used. keep expected section so we can compare the two. on the cash tab of the same output/desk_tickets.html, itemize the money: Starting checking balance (after the reset); For each ticket: how cash changed when that ticket resolved, and why (which pay / purchase, dollar amount); Ending checking balance — it must match cash_accounts in the working database. Wrong cash math loses points even if the board shows every ticket resolved. Also save: output/resolved_tickets.json — for each ticket: id, final status, short outcome, what each agent contributed, and any human approvals; output/resolved_board.html — a page you can double-click with a screenshot of your React board for each resolved ticket (101, 102, and 103). Append real runs to output/audit_trail.json. Finish output/harness.md so it covers tables, MCP tools, the five agents, API routes, the dashboard, and safety rules.

### Follow-up prompts

None yet.

### What was lacking after the first prompt

The prompt didn't say who clicks Approve or what "resolved" means when a restock can't arrive or can't be afforded, so the human approvals were made on the board under the user's name, and tickets 101 (restock ordered, waiting on vendor) and 103 (quote sent, $264 restock unaffordable with $152 left) were closed by a human after the agents finished everything the shop could do.

### What was lacking after the first prompt

The prompt asked the board to mark tickets resolved when a run finishes, but a run usually ends waiting on a human approval, so a human "Mark resolved" route (refused while approvals are pending) and a "Ready to close" status had to be added; the https URLs also had to be http, since neither dev server uses a certificate.

## Problem 10: Reflection

### Original prompt

now lets work on problem 10: reflection. open the output/desk_tickets.html and fill the reflection tab. [Then my draft answers to the five questions: how the agents performed on each ticket, Actual vs Expected for 101/102/103, what would be simpler as one agent with tools (102 and the quote math in 103), three new problems the team could solve (another out-of-stock item with an overdue invoice, another bill coming due, another club bulk discount), and three it could not (refunds/returns, late or lost shipments, cash running short before rent).] make sure that my answers tie every answer to this app and the three tickets you ran. make sure my voice is retained but refine and enter into the reflection tab. make sure i am being detailed and thorough

### Follow-up prompts

None yet.

### What was lacking after the first prompt

My draft answers were right but general, so each one had to be tied to evidence from the actual run (run IDs, dollar amounts, tool calls, token counts, and real items in the database like the out-of-stock Crest Mug and the $2,400 rent due 2026-10-02 against $152 left).

## Problem 11: Submit to GitHub

### Original prompt

now problem 11: submit to GitHub. push your code to a public GitHub repo so graders can clone it. i will have to submit the repo url to canvas and also put it in output/github_url.txt. do not push the real .env to the GitHub repo. do include both database files under data/ (the original and your working copy) so graders can run the app easily. the expected file layout is attached. README should explain: copy original DB to the working copy when you need a clean run, start mcp server, start fastapi backend, start the reach board, reset the db before a full three-ticket run.

### Follow-up prompts

None yet.

### What was lacking after the first prompt

The prompt didn't mention that .mcp.json held absolute paths to this laptop's venv, so it had to be made portable (python mcp_server/server.py, with the backend filling in the real interpreter and path) before graders could clone and run it.

