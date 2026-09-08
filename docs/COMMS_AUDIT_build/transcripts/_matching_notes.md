# Matching scratch notes (working file, safe to delete after index rewrite)

## Roster/turn table (script-derived)
01 Myk/Ser/Mel 159t 02:18-59:56(+1:04) | 02 Sp1-4 137t 00:03-1:05 | 03 Ser/Mel/Myk 53t 00:00-10:25
04 Mel/Myk/Ser 158t 00:00-51:55 | 05 Myk148/Mel/Ser 204t 00:00-47:10 | 06 Myk/Mel 93t 00:00-38:44
07 Myk/Mel 144t 02:17-36:35 | 08 Myk/Mel/Ser 112t 01:26-43:29 | 09 Ser/Sp2/Myk 25t 04:45-42:16
10 Mel118/Ser/Myk 241t 00:02-58:30 | 11 Lilla/Myk/Ser 47t 00:00-23:45 | 12 Mel/Myk/Ser 179t 00:00-57:13
13 Myk/Mel/Ser 131t 00:02-30:07 | 14 Ser/Myk/Mel 134t 00:25-31:21 | 15 Mel/Myk 88t 00:00-34:08
16 Myk152/Mel/Ser 324t 00:00-55:19 | 17 Karol/Nik 68t 00:26-22:22 | 18 Mel/Nik/Ser 172t 00:00-48:19
19 Myk/MelBahonjic 76t 00:53-22:10 | 20 Araks/Lule/Rune/Ser/Chrissy 115t 00:01-24:42
21 Sp1/Sp2 163t 00:01-59:56 | 22 Ser/Myk 49t 00:01-58:14

## KEY: timezone offset discovered
Calendar anchors appear to be ~UTC while speakers talk in CEST (+2).
- 08-14 HeyReach onboarding 08:30 == Melisa in file 01 "my meetings started at 10:30"
- 08-14 Ownership transfer 11:00 == file 04's "Friday this week ... 1PM"
Both consistent. Treat anchor clock times as UTC-ish, spoken times as CEST.

## Per-file findings

### 01 = 08-14 Ownership transfer finalization (Sergey) 11:00 — CONFIRMED
Sergey 16:40 verbatim: "The goal of this meeting is to decide whether the ownership transfer is
finalized or what has to be done to finalize the transfer of the ownership of everything related to
the lead generation infrastructure." Matches the meeting Sergey creates in file 04 ("Legion infra
ownership transfer finalization plus ownership alignment", Friday 1PM). Melisa: meetings from 10:30
until 3, "we still have another after this one and we have our one on one". Mykyta removing "the
label that Melisa asked to remove" = the DNC label Melisa complained about in file 02 -> 01 AFTER 02.
Also: Stefan hours/retainer, Chrissy new ICP system, GTM engineer per-event ownership.

### 02 = 08-14 HeyReach onboarding (Nik+Araks+Lule+Melisa) 08:30 — CONFIRMED
Screen-share walkthrough of HeyReach (+ Pipedrive) for people who want to "do more stuff on our own
without pulling your sleeve". 4 speakers = exactly the 4 anchor attendees.
- Speaker 1 = Mykyta/Nik (CONFIRMED, addressed by name, shares screen, owns the tooling)
- Speaker 2 = Melisa Draksler — INFERRED(calendar): raises the do-not-contact label problem, cites
  "Sergey by accident changed labels" (so not Sergey), owns label hygiene.
- Speaker 3 / Speaker 4 = Araks Grigoryan / Lule Salihu — INFERRED(calendar), individually
  indistinguishable. Both talk like BDRs ("it's my lead", "Mario's or Runa's campaign").
Date proof: "the lead has replied on July 31st ... but on pipedrive it was showing August something".

### 03 = 08-12 Leadgen planning 13:00 — PROBABLE
Sergey vacation Sep 1-14; "at the end of the August or September 1st we need to start with outreach
for Finovate Fall which happens ... September 15th"; "We agreed to have this kind of discussion on
Friday. There is going to be leadgen infra ownership transfer finalization" -> after file 04, before
file 01. "most likely tomorrow and on Friday" -> today = Wed 08-12. Competitor on same day:
08-12 Lead Review Meeting 15:30 (content is planning, not lead review) -> PROBABLE not CONFIRMED.

### 04 = 08-11 GTM Engineering Weekly 15:00 — CONFIRMED
Mykyta 35:09 verbatim: "Okay. So today is 11." (Aug 11 2026 = Tuesday; "this Friday" = 08-14).
Melisa 06:25: "last week ... we had this event happening and we had so many bugs" = Ai4 Aug 4-6.
Sergey 50:18-51:31 creates the 08-14 ownership-transfer meeting for 1PM/30min.
NOTE the 08-11 13:00 "GTM Eng Sync" is on the CANCELLED list, so the 15:00 Weekly is the only fit.

### 05 = 08-05 GTM Engineering Weekly 12:00 — PROBABLE
Long ownership-definition argument; Mykyta 26:04 "I'm sure for next GTM Engineering thing I also
gonna have something"; Sergey "I'm going to be out from 12pm to 4pm ... because there is a
conference day" -> mid-Ai4 (Aug 4-6). Stefan x35. Competitor: 08-05 Sales&Marketing Weekly (but
roster is the 3 GTM people only, no sales team) -> GTM Eng Weekly. Ordering: 08-05 <= 08-11 OK.

### 06 = 07-29 Melisa/Nik 11:00 — PROBABLE
2-person 1:1. Heavy DNC-list design (profile-level vs company-level exclusions, Microsoft Build
lesson), replacing Make/Smartlead auto-labeling with own n8n + own prompt, "cloud code is amazing".
Ends "I gonna eat" / "Enjoy your lunch. See you soon." Ordering forces 06 >= 07, and the only two
Melisa/Nik 1:1 anchors in range are 07-27 10:30 and 07-29 11:00 -> 06 = the later one (07-29).
Competitor: 07-29 GTM Sync 12:00 excluded (that's 3-person; 06 is 2-person).

### 07 = 07-27 Melisa/Nik 10:30 — PROBABLE
2-person 1:1. "Toby is in London right now and we will most likely get plenty of replies this week"
(London sales sprint live); "new lead was created like July 27"; Linked Helper wind-down; Zoho
rumour (Chrissy/Sergey/Carol). Ends "let's book some time for tomorrow" / "See you tomorrow".
Same-title pair with 06; ordering assigns the earlier of the two.

### 08 = 07-21 GTM team sync 13:00 — PROBABLE
Mykyta 02:06: "we had a talk with Sergey just like 20 minutes ago and we decided that the main goal
here would be ... to transfer ownership at first all of the automations". "the new sales guy also
started yesterday"; "there is nothing in August, right? It seems like there is nothing";
"maybe we can plan those changes after AI4"; "you're going to go to EdTech X in October".
=> late July, 3-person GTM roster. The "talk 20 minutes ago" = the 07-21 Nik<>Sergey 12:00 slot,
which is very likely file 09. Competitor 07-22 Sales&Marketing Weekly rejected (no sales roster).

### 09 = 07-21 Nik<>Sergey 12:00 — PROBABLE (competitor: 07-20 Nik+Sergey 08:00)
Garbled Ukrainian/Russian 2-person career/expectations 1:1: recoverable fragments = CI/CD,
versioning, developer/tester/architect, error handling, "ownership", "employee is the manager
personal development path", "expectations ... higher sales", "triggered campaigns. Volume. Reply
rate", "sales and marketing", ROI, experiments. Runs 04:45->42:16 (~12:05-12:45 if the slot is
12:00), i.e. it ends ~18 min before file 08's 13:00 start = file 08's "20 minutes ago". That
adjacency is why 07-21 12:00 beats 07-20 08:00.
Speaker 2 = Sergey Cujba — INFERRED(calendar+diarization): "Sergey Cujba" is a labeled speaker with
exactly ONE turn ("Hello") and the calendar slot is a Nik<>Sergey two-person 1:1, so Speaker 2 is
almost certainly the same voice split off by the diarizer. Still not CONFIRMED.

### 10 = 07-14 Trigger campaign sync 15:00 — CONFIRMED
Whole meeting is the trigger-based-campaign hypothesis brainstorm (title match). Melisa 00:02:
"Everything is falling apart. Like I came back ... Integration is not working" = the HeyReach
integration that landed Mon 07-13. Sergey plans "estimates ready on Tuesday, get together on
Wednesday" and "create a meeting for next week ... Friday". No competitor on 07-14.

### 11 = 07-10 ICP scoping (Lilla/Sergey) 12:00 — CONFIRMED
Lilla Szabo asks about an ICP-fit band A/B/C calculator syncing into Pipedrive; "This will probably
be taken over by Chrissy at some point ... it's her initiative". "Nice to meet you, Mykyta" (first
meeting) and "have a lovely weekend you both" => Friday. 2026-07-10 IS a Friday. Unique anchor.

### 12 = 07-10 Leadgen planning (Sergey) 10:00 — PROBABLE
Same Friday, earlier slot (so still reverse-chronological vs file 11 even within the day).
Researching trigger-campaign signal providers; sales-sprint location expansion; ClickUp priorities;
"Lulia is going to be away from August 24th to September 5th"; HeyReach ("Hayrich") integration
"ready on Monday ... latest Wednesday" (= Mon 07-13, matches known HeyReach start date);
"brew this in our heads for a weekend ... something on Tuesday" => Friday.
Competitor: 07-03 Sales Sprint Sync 10:00 — rejected because the Monday HeyReach delivery pins the
Friday to 07-10.

### 13 = 07-08 Sales Sprint Sync 09:30 — PROBABLE
"This Sprint is not going as we planned"; "hopefully by Monday we're going to have everything ready"
(= HeyReach integration, Mon 07-13); Sergey "he will most likely have functional integration until
Monday"; "it has been only two days for the week" => Wednesday (07-08 IS a Wednesday); "tasks
created by Slava on Monday morning" (= 07-06); "some of them are Monday next week" (= 07-13);
Sergey exits to "the BDR call". Only Sales Sprint Sync in the window; ordering pins the date.

### 14 = 07-03 Sales Sprint Sync 10:00 — PROBABLE
### 15 = 07-03 LinkedIn automation sync (Melisa) 09:30 — CONFIRMED
These two are BACK-TO-BACK on the same Friday and that is what fixes both.
15 (2-person Melisa/Nik): "since we got a call about right now about LinkedIn. Right." -> the call's
subject IS LinkedIn automation; whole session compares Linked Helper vs HeyReach stage-by-stage and
ends with "do you want me to buy a subscription for heyreach ... I will buy one light seat ... we
will use Sergey's profile as an experiment", then "let's jump on another meeting. See you in a minute."
14 starts moments later (Sergey at 00:25, greetings at 03:07, Melisa "I don't think that will be a
late") and ENDS with Sergey: "I shared the credentials for Hey, Rich already in the channel" =
Sergey's LinkedIn profile creds promised in 15. 14 is sales-sprint content (Sales Navigator
enterprise seats, Toby's campaign resumed, conference attendee scraping) and closes "Have a great
weekend" => Friday. 2026-07-03 IS a Friday. 09:30 -> 10:00 also preserves reverse-chron within the day.

### 16 = 06-29 Sales Sprint Sync (Melisa+Sergey) — PROBABLE
Lead-score table walkthrough (0-110, hiring-signal waterfall, employees 50-500), then Nordic/Norway
sprint sizing (~8,000 people, "for one month"), Germany+Switzerland cited as the previous sprints,
"we should make that happen ... until July 20th. July 15th", "should we schedule like some maybe
weekly meeting for us to discuss such things?" (the weeklies don't exist yet).
Melisa 54:18: "I'm going to be absent like most of the Wednesday ... I have a hospital appointment"
-> Wednesday 07-01, and 07-01 Lead Review is on Nik's CANCELLED list. Nice corroboration.
Ordering forces this slot: 16 must be older than 17 (06-25 11:00) and newer than 15 (07-03), and
06-29 is the only anchor left in that window.

### 17 = 06-25 Intro Karol 11:00 — CONFIRMED
Person-a2ef1b69: "Hey, how are you doing and welcome to the team ... where are you based by the way?"
Nik: "I'm in Ukraine"; Karol "I'm based in Poland"; both complain about ~30C heat. First-contact
intro + scope-of-responsibilities exchange + a LinkedIn-post-scraping idea Karol wants to co-build.
Unique anchor, unique participant.

### 18 = 06-25 GTM Sync (Melisa+Sergey) 09:15 — PROBABLE
Melisa + Nik + Sergey, 48 min, UK Sales Sprint prep: Nik's artifact, 30,000-person expanded list,
Trigify, government/non-profit domain exclusions, messaging simplification for Toby (on sick leave).
Nik 00:39: "only three weeks left" before the sprint has to start. Sergey re a vendor conversation:
"this is like a four months ... ago. I think it was in February" => the meeting is in June.
Ends "I think that we can switch to BDRC then" (the BDR call). 09:15 keeps it earlier in the day
than file 17's 11:00, preserving reverse-chron. Competitor: 06-19 Sync (Melisa) 11:10 — rejected
because that slot is needed by file 19 and because 18 must be newer than 19.

### 19 = 06-19 Sync (Melisa) 11:10 — PROBABLE
Melisa Bahonjic (NOT Draksler) + Mykyta, 22 min, Friday ("Have a great weekend" / "See you Monday").
She has just got married and is re-registering her documents ("deadline until next Wednesday");
Mykyta has a visible face/hand injury from an incident. Content: Clay/workspace login lockout
troubleshooting, 11,600 contacts built for "Toby's first sprint", AI4-in-August staffing (Stefan?
Rune and Mario attending), and coaching Nik not to become someone's personal assistant.
2026-06-19 IS a Friday. Competitor: 05-29 Mykyta&Melisa Sync 11:30 (also a Friday) — REJECTED: on
05-29 Mykyta was on day 2 after his 05-28 induction and could not already have an 11,600-row table.

### 20 = 06-18 All-team — PROBABLE (weakest match in the set)
Araks Grigoryan, Lule Salihu, Rune Jensen, Sergey Cujba, Chrissy Winkler; 25 min; conference-support
planning off the ClickUp conference list. Sergey opens "we shouldn't have any topics for discussion
because the silent season is getting started" = a recurring slot with no agenda. Rune is explicitly
a new onboardee ("as a new onboardy", "there's a lot of stuff in that onboarding list"). Ai4 is
future ("August 4th through the 6th"). Sergey closes: "we will need to get back to the discussion
about the conferences and support when Toby and Mario and Jim can join. It's going to be either next
week on sales and marketing meeting" -> so this is NOT the Sales&Marketing Weekly, and Toby/Mario/Jim
were absent. "All-team" is the only remaining anchor that gathers this cross-functional group, and
06-18 is the only All-team date inside the ordering window (07-16 All-team is excluded by ordering).
Treated as PROBABLE with a partial-turnout caveat; a reasonable alternative verdict is UNMATCHED.

### 21 + 22 = 06-16 Sergey<>Mykyta 11:00 — PROBABLE (one shared anchor)
SPEAKER CORRECTION vs the old index: file 22's labels are RIGHT and map onto 21 as
Speaker 1 = Sergey Cujba, Speaker 2 = Mykyta Krivosheya (the old index had Speaker 1 = Mykyta).
Evidence: Speaker 2 says "як я докладую тебе, там два артефакти" and built the Apify enrichment /
Clay table (Nik is the artifact-preparer, cf. file 18 "I also prepared for artifact as always");
Speaker 1 owns the historical sequences ("ті меседжі, які у нас пішли нормально по Германії і
нормально по Швейцарії") and coaches on job-title coverage (program manager, Head of Data/AI/ML) =
Sergey. Speaker 1 also sends the Fireflies audio for re-upload with Ukrainian selected, which is why
file 22 exists as an English-engine mis-transcription of the same 64 minutes.
Content: UK sales-sprint sequence review + "UK Tech Leader" Clay table (DNC-companies formula,
government/university domain exclusion, dedupe by company URL), and the person-level vs
company-level do-not-contact debate. They agree to reconvene "в четвер ... приблизно такий же час".
Competitor: 06-08 Sergey<>Mykyta 09:00 — rejected because the Clay build shown is already mature
(~2 weeks in fits better than ~1 week) and because file 20 (06-18) must be newer.

## ORDERING CROSS-CHECK — PASS
01 08-14 | 02 08-14 | 03 08-12 | 04 08-11 | 05 08-05 | 06 07-29 | 07 07-27 | 08 07-21 | 09 07-21
10 07-14 | 11 07-10 | 12 07-10 | 13 07-08 | 14 07-03 | 15 07-03 | 16 06-29 | 17 06-25 | 18 06-25
19 06-19 | 20 06-18 | 21 06-16 | 22 06-16
Monotonically non-increasing, no violations. The three same-date pairs (01/02, 11/12, 14/15, 17/18)
are ALSO reverse-chronological at clock-time resolution. No anchor used twice (21+22 share one).
Counts: CONFIRMED 7 (01,02,04,10,11,15,17) · PROBABLE 15 · UNMATCHED 0.
