# Requirements Document

**Feature:** Post helper (sample from the PostPal playground)
> `.kiro/specs/post-helper/requirements.md`. The one must-have slice for the 21 Nov build. Written in Kiro's
> requirements format: user stories with EARS acceptance criteria. Design and tasks come next in the
> spec-driven flow and are not written here.
## Introduction
An author on a micro-blogging site can ask PostPal about their own past posts and ask for a draft of a new
one. A draft is only published after the author confirms. Posts come from seed data; a published post is saved to
`data/published.json`, and there is no real publishing API (see `tech.md`, "Bootcamp build target").
## Scope for the bootcamp slice
- **In:** finding posts by topic, an honest answer when nothing matches, drafting a post of at most 280
  characters, confirm or cancel before publishing, an answer in the language of the question.
- **Out:** a real publishing API, real sign-in, hashtag suggestions and tone memory (should have, later), the
  weekly summary (could have, later).
## Glossary

- **PostPal**: The Strands agent that helps an author find past posts and write drafts.
- **Author**: The person who uses PostPal on a micro-blogging site.
- **Draft**: A post text of at most 280 characters that waits for the Author to confirm or cancel it.

## Requirements

### Requirement 1: Find my posts
**User Story:** As an author, I want to ask about a topic and see my own posts on it, so that I do not
write the same thing twice.
#### Acceptance Criteria
1. WHEN the author asks about a topic THEN the system SHALL call `find_posts` with that topic and answer
   only from the posts it returns.
2. The system SHALL return at most three posts, newest first.
3. IF no post matches the topic THEN the system SHALL say that no post was found and SHALL NOT invent one.
4. WHEN the author asks in Thai THEN the system SHALL answer in Thai; WHEN in English, in English.
### Requirement 2: Draft with a confirmation
**User Story:** As an author, I want a draft I can approve or cancel, so that nothing goes out that I did
not choose.
#### Acceptance Criteria
1. WHEN the author asks for a draft THEN the system SHALL return a draft of at most 280 characters and
   SHALL NOT publish it.
2. WHEN the author confirms THEN the system SHALL save the draft to the author's posts so a later search can find
   it, and show "published".
3. IF the author cancels THEN the system SHALL NOT publish and SHALL record a cancelled draft.
4. IF the draft is longer than 280 characters THEN the system SHALL shorten it before showing it.
### Requirement 3: When the lookup fails
**User Story:** As an author, I want a clear message when the search is unavailable, so that I am not
given a made-up answer.
#### Acceptance Criteria
1. WHILE the posts store is unreachable the system SHALL tell the author it cannot search right now.
2. WHILE the posts store is unreachable the system SHALL NOT answer from memory or guess.
3. WHEN the store is reachable again THEN the system SHALL answer the next question as normal.
## Agent design
The part of this feature that needs an AI agent. P7 builds `agent.py` from this section, and the 21 Nov design starts from it.
Fixed rules and screens stay out of the agent.
- **Job:** find the author's own posts on a topic and write a draft of at most 280 characters, without ever publishing.
- **System prompt** (`agent/prompts.py`): "You are PostPal, a helper for authors on a micro-blogging site. When the author asks about their past posts, search with find_posts. Only quote posts that find_posts returned. If it returns none, say so and do not invent one. When the author asks for a draft, write it in their tone and save it with save_draft. Never say a post is published; the app asks the author to confirm first. If a tool says the store is unreachable, say you cannot search right now and do not guess. Answer in the language of the question, in two or three short sentences."
- **Tools** (seed data in `data/posts.json` for now):

| Tool | Takes | Returns |
|---|---|---|
| `find_posts` | a topic, in Thai or English | up to three posts, newest first, or "No posts found about that topic." |
| `save_draft` | the draft text | "Draft saved." and a request to confirm, or "Draft too long" if it is over 280 characters. It never publishes. |

- **Kept out of the agent:** publishing and cancelling are plain code the app runs after the author answers, so the agent has no
  publish tool. The 280-character limit is checked in code, not in the prompt.
## Success criteria
| Sample KPI | How this spec tests it |
|---|---|
| Every draft is 280 characters or fewer | a test over 10 drafts checks `len(text) <= 280` |
| Zero invented posts | 20 questions, 5 of them on topics with no match; every quoted post exists in the seed data |
| Zero posts published without a confirmation | the cancel test and the no-confirm test both end with nothing published |
| Answer in under 5 seconds | time from the question to the answer on Haiku 4.5 |
## Demo script for the 22 Nov pitch
1. Ask "what did I write about running?"; show two posts, newest first.
2. Ask about a topic with no posts; show the honest "none found".
3. Ask for a draft; show it, then cancel; show nothing published.
4. Ask again, confirm; show "published".
