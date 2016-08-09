Everything will be deployed in Docker containers
===============
Main Application: Where everything will plug in -- everything
can be plugged in through a new URL route:
	Flask -- application server
	Tornado -- web server (allows production-level server)

	API: Open to URL routes for additional pages

Authentication: Covered through basic Flask authentication
	Flask -- login plug-in applied

	API: Plug into main application via adding "/user" route

Gamification: Uses a separate SQL DB for the users and their corresponding
coins, points, achievements, priority (five-column SQL DB, which we 
temporary call "game"):
	Coins: 
		Integrate by simply using new column in "game"

	Points:
		Integrate by simply using new column in "game"

	Achievements: Stored in a separate SQL DB (since no user should be able to
	unlock the same achievement twice). This SQL DB will have a row for each
	user and a column for each possible achievement (the values will be 
	True/False). We temporarily call this DB "achievements":
		Simply adds a means of earning points
		Since not used for anything else, no other dependencies, and will not
			mess anything up (unless points container not activated)
		App will pull from DB and display the most relevant acheivements from
			"achievements"
		If anything is completed, it will be marked true in "achievements" 
			(can accessed by the app even when container is not activated)

	Levels/Abilities:
		No need to store "abilities" in "game" -- inherently embedded into the
			levels number (unless decide to use some form of branching abilities)
		Integrate by using new column in "game"
		Similar to how some page require login (in the Flask), we'll have
			certain URLs require a particular level to access. Thus, if this
			module is not activated, all such pages will be deactivated (since
			level will be 1 be default or something of the sort); works otherwise

	Payment:
		Interface w/ existing payment system APIs (Venmo, Paypal, 
			Credit Cards, etc...)
		Take payment and simply add to the coins attributes in "game"

	Resume Board:
		Integrate into main application through "/board" route
		Pulls from "game" and organizes users by priority
		Should update synchronously (would be too chaotic to see names 
			flying around while on page)

	Expert Charges:
		Integrate through "/experts" route
		Add feature that uses this DB and sorts by points attribute (roughly
			corresponds to "experience")
		Make a request feature that pushes request to user
		User reviews and accepts/rejects the request (equivalent to making changes
			to the resume)
		If accepts, transfers the coins over from one to another account (must
			be very secure) -- also MUST check that the balance > request amount

Version Control:
	Interface through "/resume" route on main app
	Pulls from separate Resume Mongo DB

Comments:
	Integrated on Resumes -- another field in Mongo

To-Do List:
	Auto-Populate with the comments
	Another field in users