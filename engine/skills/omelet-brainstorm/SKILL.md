---
name: omelet-brainstorm
description: Use when the owner describes an app, a site, a tool, or a change to an existing project in plain words and no written brief or spec exists for it yet — "I want a website for my bakery", "can you add customer accounts", "I have an idea". Use it before naming any technology or writing any code, even when the idea sounds simple, because the questions it asks are what the stack choice and the plan are built from.
---

# Turning an idea into a brief

The owner is not technical. They describe an outcome, not a system, and they leave out
everything they consider obvious: who will log in, who will change the text next month, what
the first useful version is. Code written from a one-sentence idea guesses at all of that, and
the guesses are what the owner later calls "not what I meant".

This skill asks the questions whose answers decide those things, in words the owner can answer,
and writes the result down so the next session (or the other coding agent sharing this VM) does
not ask again. The answers are exactly what `omelet-stack` needs to choose a stack and what
`omelet-plan` needs to plan the first slice — that is why this happens before either.

## Interview rules

- **One question per message.** The owner answers in chat; two questions get one answer.
- **Offer choices with plain examples.** "Who will use it: just you, people in your company, or
  customers and the public?" is answerable; "what are the user roles?" is not.
- **Skip what the description already answered**, and say what you understood before asking on:
  "So it's a site for the bakery that your sister updates weekly. One thing I want to check: …"
- **Scale to the request.** The list below is a ceiling, not a script. A description that
  already answers everything gets one message that reflects it back and asks "did I get this
  right?". A page with opening hours does not get ten questions.
- **No technology words.** Ask about people, content, money, memory and outside things. The
  owner cannot answer a question they do not understand, and a wrong guess at "yes" costs a
  rebuild.

  | Do not say | Say instead |
  |---|---|
  | database, store data | "remember things between visits" |
  | CMS, admin panel | "someone changes the text, pictures or products themselves" |
  | login system, auth, roles | "who uses it, and does anyone need their own account" |
  | API, integration | "does it connect to anything else you already use" |
  | AI, LLM, model | "should it answer questions or write things on its own" |
  | hosting, deploy, server | "will it stay on this computer or go online for others" |

- **Reflect back, then write.** End with the brief in plain words and ask whether it is right.
  Write the file only after a yes. A brief the owner has not confirmed is still a guess.

## The question list

Ask only the rows the description leaves open, in this order.

| Ask about | What it decides |
|---|---|
| What it is and who it is for, in a sentence or two | the shape of the project |
| Who uses it: only you, your team, or customers and the public | accounts, roles, public exposure |
| The three main things a person should be able to do there | screens, the first slice |
| Will someone who is not a developer change text, pictures or products regularly | whether an editing screen exists |
| Does it need to remember things between visits: accounts, orders, bookings, notes | what is stored |
| Should it answer questions, summarize or write things on its own | smart features, and whether documents are processed |
| Does it connect to anything else: payments, email, a calendar, a spreadsheet | outside services, payments |
| Will it stay on this computer or go online later; is there hosting already | where it will live |
| What is the smallest version that would already be useful | the first slice |
| A site whose look you like; the language(s) it should speak | look and feel |

## New project: write `docs/brief.md`

Fixed sections, in this order. A section that does not apply says "none" rather than
disappearing, so a later reader knows it was asked.

```markdown
# <Project name> — brief

## What it is
A website for Marta's bakery: where it is, when it opens, and the menu with photos.

## Who uses it
Customers and the public, no accounts. Marta's sister edits it.

## What they can do
See opening hours and address · browse the menu with photos · call or find the shop.

## Content and who edits it
Menu items, prices and photos change weekly, edited by the sister, who is not technical.

## What it remembers
Nothing about visitors.

## Outside services
None. (Later: Google Maps embed.)

## Smart features
None.

## Where it will live
On this computer for now; will go online with cheap shared hosting.

## First slice
Home page with hours and address, menu page with photos, an editing screen the sister can use.

## Later
Online ordering (asked, not now).

## Look and feel
Warm, simple, like <site the owner named>. Polish and English.
```

Then **use `omelet-stack`**.

## Change to an existing project: write `docs/specs/<date>-<slug>.md`

Read `docs/brief.md` first, so questions build on what is already known rather than repeating
it. If the change alters a section of the brief (new kind of user, new outside service), update
that section too.

```markdown
# Customer accounts — spec

## What changes for the owner
Customers can create an account, see their past orders and reorder.

## Who it affects
Customers (new: accounts). Staff see the customer's name on orders.

## What it needs from outside
Email, to confirm an address and reset a password.

## Not in this change
Loyalty points, social login.

## How we will know it works
The owner can create an account in the browser, place an order, log out, log in and see it.
```

Then **use `omelet-plan`**.

## Common mistakes

- Asking two things in one message. The owner answers the second one.
- Asking about databases, frameworks or hosting providers. Ask what it should remember and
  where it will live.
- Writing the brief before the owner has said the summary is right.
- Running the whole list for a landing page. Reflect back, confirm, move on.
- Treating "later" items as part of the first slice. They go in *Later* and stay there.
