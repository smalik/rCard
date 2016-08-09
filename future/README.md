Revised Plan (Updated what "services" are)
1. Authentication: Just the standard login/logout/session part of the app. This
section is partly in place, but requires heavy testing to make sure there aren't
security flaws. 

2. Version Control: Feature for doing pulls/pushes/commits/etc... and doing so
while also enabling a traversal back through revisions. There's definitely plenty
of changes that need to be made on this front, specifically:
	- Make it so that the history is traversable. Right now, whenever someone forks
		an instance of someone's resume, even if that resume was produces as a result
		of some previous revisions, you can't trace that back. 

		As in, let's say there are persons A, B, and C. B forks A's resume, makes
		edits, pushes them back, and A accepts them. Now, if C branches A's resume
		(after these changes were accepted), the changes WILL be reflected, but we
		will NOT know from where the changes came (as in, there's no way to connect
		the pulled resume to person B). 

		In that line, also make it so that you can undo/reverse changes. Currently,
		this is not possible -- once you accept someone's changes, your original
		version is overwritten.
	- Make it possible to pull from pushes instead of just the current version of 
		a resume in a person's account (don't know if that'd be a security/personal
		issue for people -- we could make it an option you can toggle on/off from
		your account)
	- Make it possible for MULTIPLE people to work on the same branch. Almost
		identical to the concept of git branches, we should have it so that people
		can simulataneously work on a branch before pushing back up.
	- (This'd definitely be for later down the road
		when we have time to add additional features) but make an offline
		interface. That way, people can pull resumes when they're online, work
		offline, and then push them back when they reconnect.

3. Comments: Feature for dropping comments and up/down voting them:
	- Make comments system where reviewers can pin issues to particular sections
		of the resume and user can see heatmap of concentrations
	- Also do analytics of the text in comments to automatically produce
		a checklist of things the owner should work on/do
	- Display the users who dropped the most comments on your resume
	- Allow filtering of the comments (by topic/user/etc)

4. Gamification/Monetization: I see gamification as a huge part of the monetary
strategy. Of course, I'm not too experienced with actual "business," so these
are mostly based off of my personal feelings from using other products. But here:

Overview
===============================================================================
	- The whole system will centralize around a coin and points system. As with
		most game features, you'll theoretically be able to use the app for free.
		But, you'll always have the option to pay actual money to increase the
		number of coins you have in your account.
	- As an overview, coins are the primary internal monetary exchange mechanism --
		as mentioned above, there is a means of going from real money -> coins. As
		is explained below, the system ALSO allows you to do the reverse -- that is
		transform coins -> real money (not too sure about the viability of this?)
	- The other main game entity are "points" -- these are purely fictitious,
		internal entities. Points are akin to XP in any mainstream game -- you will
		gain XP from doing various activities (described in "Usage" below), which
		will elevate your "level"
	- Whenever you increase your level, you will not only gain additional coins
		for free, but also unlock new "abilities" (specifics all given in Usage)
	- Summary: Each account will have the following four properties:
		- Coins
		- Points
		- Level
		- Abilities

Usage
===============================================================================
	- When anyone makes an account, we will set these default values:
		- Coins: 500
		- Points: 0
		- Level: 1
		- Abilities: Basic
	- Before progressing any further, I want to comment on the earlier note about
		being able to transform coins -> real money. Using the scale 1 coin = 1 cent, 
		it'd seem that we're giving out $5 to each person who signs up. BUT, to
		prevent dishing out free cash, we'll make it so that you only
		unlock this ability after reaching Level 5 on the system. That is, all
		coins are held internally until you gain enough XP for Level 5

	- The following is a rough illustration of the gamified system (numbers
		are only given as temporary placeholders/scale)

	- Gaining Coin/Points:
		- When you refer someone else, who reaches Level 5: 500 coins. This will
			primarily be a strategy for early stages of use

		- We'll also have various "achievements" that give you points:
			- Created First Resume: 50 pts
			- Forked First Resume: 50 pts
			- Reviewed First Resume: 50 pts
			- Owner accepted Your Changes: 100 pts
			- Became Primary Commenter on Resume: 100 pts
			- Owner gets accepted to job with you 
				as editor: 150 pts (varies on how much of the resume you edited)
			- etc...

	- Using Coins:
		- Whenever you create a resume, you'll have the option to either watch an 
			ad or pay a certain number (50) of coins
		- Have an overhead fee when transferring money out of the system --
			a certain number to transfer coins -> real money (50)
		- Promoting your resume -- we'll have a "public resume board." This
			board will be accessible by everybody, meaning having your resume 
			displayed on the top of that board will attract a lot of attention 
			and get people looking into your resume. Each resume will have a
			"priority" value associated with it, which you can boost by pumping
			in coins (i.e. 500 coins -> "priority score" of 5), and the board will
			simply display all the resumes filtered by this value. This score can
			go arbitraily high, meaning people can spend as much as they wish. 
			Further, these priority scores will depreciate over time, meaning,
			if you pump in 500 coins one morning, the next it'll be 400, then 300, 
			and so on. In this way, you can also "revive" your resume to the top
			by spending more coins.

	- As for upgrading levels and unlocking abilities, people prefer to get
		constant feedback reminding them that they're actually accomplishing
		something. So, it's better to have more, less separated levels. 
		Here are some large benchmark points, with their associated unlocks 
		(the in-between things can have small unlocks, such as unlocking
		different app backgrounds or avatar customizations). Also, every 
		level you increase, you get 250 coins:
		- Level 1 (Novice): 0 pts
			- Create/edit/review/revise/comment on resumes (basic)
		- Level 5 (Apprentice): 250 pts
			- Cash out coins -> real money
		- Level 15 (Mighty): 1000 pts
			- Free "Publicity Upgrade" (one-time use thing that boosts you
				to the top of the resume board)
		- Level 25 (Master): 10000 pts
			- Ability to add an additional "Expert Cost" (explained below)
		- Level 50 (Legend): 100000 pts

	- "Expert Cost" is the ability for users to charge an overhead fee (i.e.
		they'll send requests to users to make edits, saying "I want 50 coins"
		extra). The intention is that people who achieve this ability are
		sufficiently experienced with editing resumes and have proven themselves
		enough to be able to charge extra
			- Leaderboard system of users will be implemented (ordered by scores)
			- Can "hire" these editors -- will charge coins from account (we
				can charge an overhead fee here)
			- Editors can do opposite and "request" to do work from you

5. Jobs Matching: Jobs matching algorithm -- not too much to say here that hasn't
been said already. Not sure how in-depth the current matching thoughts are, but what
I was thinking for a very high-level model was (if we go with the original w2v idea) 
consider the vector in this space and how it swings overtime. So, this vector will
basically have an "n-dimensional momentum," which (hopefully) follows some sort of
consistent path that can be traced forward for however far we wish to predict

6. Importing: Feature for reading in resumes from already existing formats. This'll
definitely ease the transition from current infrastructure to rCard, crucial for
people actually adopting this. We will be able to translate:
	- Word
	- PDF
	- LinkedIn
	- Plain Text/HTML