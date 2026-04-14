import os
from decimal import Decimal

from django.core.management.base import BaseCommand


SKILL_CATEGORIES = [
    {"name": "Woodworking", "icon": "\U0001fab5", "color": "#8B4513", "description": "Working with wood"},
    {"name": "Electronics", "icon": "\u26a1", "color": "#FFD700", "description": "Circuits, soldering, and electronics"},
    {"name": "Cooking", "icon": "\U0001f373", "color": "#FF6347", "description": "Cooking and baking"},
    {"name": "Art & Crafts", "icon": "\U0001f3a8", "color": "#9370DB", "description": "Drawing, painting, and crafts"},
    {"name": "Coding", "icon": "\U0001f4bb", "color": "#00CED1", "description": "Programming and software"},
    {"name": "Outdoors", "icon": "\U0001f33f", "color": "#228B22", "description": "Outdoor projects and nature"},
    {"name": "Sewing & Textiles", "icon": "\U0001f9f5", "color": "#FF69B4", "description": "Sewing, knitting, and textiles"},
    {"name": "Science", "icon": "\U0001f52c", "color": "#4169E1", "description": "Science experiments and research"},
]

SKILLS_BY_CATEGORY = {
    "Woodworking": [
        {"name": "Measuring & Marking", "icon": "\U0001f4d0", "locked": False, "prereqs": [],
         "levels": {"1": "Eyeballer", "2": "Precise", "3": "Dead-On", "4": "Master Measurer", "5": "Micron Maniac"}},
        {"name": "Hand Tools", "icon": "\U0001fa9a", "locked": False, "prereqs": [],
         "levels": {"1": "Sawdust Maker", "2": "Handy", "3": "Skilled", "4": "Artisan", "5": "Old School Master"}},
        {"name": "Power Tools", "icon": "\u26a1", "locked": True, "prereqs": [("Hand Tools", 2)],
         "levels": {"1": "Nervous", "2": "Comfortable", "3": "Confident", "4": "Power User", "5": "Shop Boss"}},
        {"name": "Sanding & Finishing", "icon": "\U0001fab5", "locked": False, "prereqs": [],
         "levels": {"1": "Rough", "2": "Smooth Operator", "3": "Satin Touch", "4": "Glass Finish", "5": "Mirror Polish"}},
        {"name": "Joinery", "icon": "\U0001f517", "locked": True, "prereqs": [("Hand Tools", 3), ("Measuring & Marking", 2)],
         "levels": {"1": "Glue & Pray", "2": "Butt Joints", "3": "Dado & Rabbet", "4": "Dovetailer", "5": "Mortise Master"}},
        {"name": "Wood Selection", "icon": "\U0001f333", "locked": True, "prereqs": [("Hand Tools", 2)],
         "levels": {"1": "Pine Only", "2": "Grain Reader", "3": "Species Spotter", "4": "Wood Whisperer", "5": "Lumber Sage"}},
    ],
    "Electronics": [
        {"name": "Wiring & Connectors", "icon": "\U0001f50c", "locked": False, "prereqs": [],
         "levels": {"1": "Wire Stripper", "2": "Connector", "3": "Clean Runs", "4": "Cable Artist", "5": "Harness Pro"}},
        {"name": "Through-Hole Soldering", "icon": "\U0001f525", "locked": False, "prereqs": [],
         "levels": {"1": "Cold Joints", "2": "Tin Tipper", "3": "Clean Cones", "4": "Solder Surgeon", "5": "Flux Master"}},
        {"name": "SMD Soldering", "icon": "\U0001f52c", "locked": True, "prereqs": [("Through-Hole Soldering", 3)],
         "levels": {"1": "Shaky", "2": "Steady", "3": "Drag Soldier", "4": "Micro Surgeon", "5": "SMD Wizard"}},
        {"name": "Circuit Reading", "icon": "\U0001f4cb", "locked": False, "prereqs": [],
         "levels": {"1": "Confused", "2": "Symbol Reader", "3": "Trace Follower", "4": "Schematic Thinker", "5": "Circuit Sage"}},
        {"name": "Circuit Design", "icon": "\u270f\ufe0f", "locked": True, "prereqs": [("Circuit Reading", 2)],
         "levels": {"1": "Copy Cat", "2": "Modifier", "3": "Original", "4": "Architect", "5": "Analog Guru"}},
        {"name": "Microcontrollers", "icon": "\U0001f916", "locked": True, "prereqs": [("Wiring & Connectors", 2), ("Circuit Reading", 2)],
         "levels": {"1": "Blinky LED", "2": "Sensor Reader", "3": "Multi-Input", "4": "IoT Builder", "5": "Embedded Wizard"}},
        {"name": "PCB Layout", "icon": "\U0001f7e9", "locked": True, "prereqs": [("Circuit Design", 3)],
         "levels": {"1": "Auto-Route", "2": "Manual Route", "3": "Multi-Layer", "4": "High-Speed", "5": "PCB Artist"}},
    ],
    "Cooking": [
        {"name": "Knife Skills", "icon": "\U0001f52a", "locked": False, "prereqs": [],
         "levels": {"1": "Careful Chopper", "2": "Dicer", "3": "Julienne", "4": "Brunoise", "5": "Speed Demon"}},
        {"name": "Heat Control", "icon": "\U0001f525", "locked": False, "prereqs": [],
         "levels": {"1": "Burner", "2": "Temp Watcher", "3": "Heat Surfer", "4": "Flame Dancer", "5": "Thermal Master"}},
        {"name": "Baking", "icon": "\U0001f9c1", "locked": False, "prereqs": [],
         "levels": {"1": "Box Mix", "2": "From Scratch", "3": "Baker", "4": "Pastry Cook", "5": "P\u00e2tissier"}},
        {"name": "Flavor & Seasoning", "icon": "\U0001f9c2", "locked": False, "prereqs": [],
         "levels": {"1": "Salt & Pepper", "2": "Herb User", "3": "Spice Blender", "4": "Palate Pro", "5": "Flavor Architect"}},
        {"name": "Meal Planning", "icon": "\U0001f4dd", "locked": True, "prereqs": [("Knife Skills", 2), ("Heat Control", 2)],
         "levels": {"1": "One Dish", "2": "Full Meal", "3": "Week Planner", "4": "Meal Prep Pro", "5": "Executive Chef"}},
        {"name": "Food Safety", "icon": "\U0001f321\ufe0f", "locked": False, "prereqs": [],
         "levels": {"1": "Hand Washer", "2": "Temp Checker", "3": "Cross-Contam Aware", "4": "HACCP Thinker", "5": "Safety Inspector"}},
        {"name": "Plating & Presentation", "icon": "\U0001f37d\ufe0f", "locked": True, "prereqs": [("Knife Skills", 3), ("Flavor & Seasoning", 2)],
         "levels": {"1": "Pile It On", "2": "Neat", "3": "Composed", "4": "Restaurant Ready", "5": "Edible Art"}},
    ],
    "Art & Crafts": [
        {"name": "Drawing", "icon": "\u270f\ufe0f", "locked": False, "prereqs": [],
         "levels": {"1": "Sketcher", "2": "Renderer", "3": "Illustrator", "4": "Fine Artist", "5": "Visionary"}},
        {"name": "Painting", "icon": "\U0001f58c\ufe0f", "locked": False, "prereqs": [],
         "levels": {"1": "Brush Holder", "2": "Color Mixer", "3": "Blender", "4": "Painter", "5": "Gallery Ready"}},
        {"name": "Color Theory", "icon": "\U0001f308", "locked": False, "prereqs": [],
         "levels": {"1": "Primary Knower", "2": "Complementary", "3": "Harmonizer", "4": "Palette Master", "5": "Color Sage"}},
        {"name": "Sculpture & 3D", "icon": "\U0001f5ff", "locked": True, "prereqs": [("Drawing", 2)],
         "levels": {"1": "Clay Smasher", "2": "Former", "3": "Sculptor", "4": "3D Thinker", "5": "Installation Artist"}},
        {"name": "Digital Art", "icon": "\U0001f4bb", "locked": True, "prereqs": [("Drawing", 2), ("Color Theory", 2)],
         "levels": {"1": "Pixel Pusher", "2": "Layer User", "3": "Digital Painter", "4": "Vector Wizard", "5": "Creative Technologist"}},
        {"name": "Textile & Fiber", "icon": "\U0001f9f6", "locked": False, "prereqs": [],
         "levels": {"1": "Tangler", "2": "Stitcher", "3": "Pattern Follower", "4": "Pattern Maker", "5": "Fiber Artist"}},
    ],
    "Coding": [
        {"name": "Logic & Algorithms", "icon": "\U0001f9e9", "locked": False, "prereqs": [],
         "levels": {"1": "If-Then", "2": "Looper", "3": "Sorter", "4": "Optimizer", "5": "Algorithm Designer"}},
        {"name": "Python", "icon": "\U0001f40d", "locked": False, "prereqs": [],
         "levels": {"1": "Print Hello", "2": "Script Writer", "3": "Module User", "4": "Package Builder", "5": "Pythonista"}},
        {"name": "Web Development", "icon": "\U0001f310", "locked": False, "prereqs": [],
         "levels": {"1": "HTML Writer", "2": "CSS Styler", "3": "JS Scripter", "4": "Full Pager", "5": "Web App Builder"}},
        {"name": "Hardware Programming", "icon": "\U0001f527", "locked": True, "prereqs": [("Python", 2)],
         "levels": {"1": "LED Blinker", "2": "Sensor Reader", "3": "Actuator Controller", "4": "System Builder", "5": "Hardware Hacker"}},
        {"name": "Data & Visualization", "icon": "\U0001f4ca", "locked": True, "prereqs": [("Python", 2)],
         "levels": {"1": "CSV Reader", "2": "Chart Maker", "3": "Data Cleaner", "4": "Analyst", "5": "Data Storyteller"}},
        {"name": "Version Control", "icon": "\U0001f4c2", "locked": False, "prereqs": [],
         "levels": {"1": "Saver", "2": "Committer", "3": "Brancher", "4": "Merger", "5": "Git Wizard"}},
    ],
    "Outdoors": [
        {"name": "Gardening", "icon": "\U0001f331", "locked": False, "prereqs": [],
         "levels": {"1": "Seed Planter", "2": "Waterer", "3": "Grower", "4": "Green Thumb", "5": "Garden Designer"}},
        {"name": "Tool Maintenance", "icon": "\U0001f527", "locked": False, "prereqs": [],
         "levels": {"1": "Cleaner", "2": "Sharpener", "3": "Oiler", "4": "Restorer", "5": "Tool Whisperer"}},
        {"name": "Nature ID", "icon": "\U0001f343", "locked": False, "prereqs": [],
         "levels": {"1": "Looker", "2": "Spotter", "3": "Identifier", "4": "Naturalist", "5": "Field Expert"}},
        {"name": "Building & Construction", "icon": "\U0001f3d7\ufe0f", "locked": True, "prereqs": [("Woodworking::Measuring & Marking", 2)],
         "levels": {"1": "Stacker", "2": "Leveler", "3": "Framer", "4": "Builder", "5": "Architect"}},
        {"name": "Water Systems", "icon": "\U0001f4a7", "locked": True, "prereqs": [("Tool Maintenance", 2)],
         "levels": {"1": "Hose User", "2": "Sprinkler Setter", "3": "Drip Designer", "4": "Irrigation Pro", "5": "Hydro Engineer"}},
    ],
    "Sewing & Textiles": [
        {"name": "Hand Sewing", "icon": "\U0001faa1", "locked": False, "prereqs": [],
         "levels": {"1": "Button Sewer", "2": "Straight Stitcher", "3": "Hem Maker", "4": "Hand Tailor", "5": "Couture Stitcher"}},
        {"name": "Machine Sewing", "icon": "\U0001f9f5", "locked": True, "prereqs": [("Hand Sewing", 2)],
         "levels": {"1": "Threader", "2": "Straight Lines", "3": "Curves", "4": "Pattern Sewer", "5": "Machine Master"}},
        {"name": "Pattern Reading", "icon": "\U0001f4d0", "locked": False, "prereqs": [],
         "levels": {"1": "Confused", "2": "Piece Finder", "3": "Layout Pro", "4": "Modifier", "5": "Pattern Drafter"}},
        {"name": "Fabric Selection", "icon": "\U0001f3ea", "locked": True, "prereqs": [("Hand Sewing", 2), ("Pattern Reading", 2)],
         "levels": {"1": "Cotton Only", "2": "Woven vs Knit", "3": "Fabric Matcher", "4": "Textile Expert", "5": "Fabric Sommelier"}},
    ],
    "Science": [
        {"name": "Observation", "icon": "\U0001f441\ufe0f", "locked": False, "prereqs": [],
         "levels": {"1": "Looker", "2": "Noticer", "3": "Recorder", "4": "Analyst", "5": "Scientific Observer"}},
        {"name": "Measurement", "icon": "\U0001f4cf", "locked": False, "prereqs": [],
         "levels": {"1": "Ruler User", "2": "Multi-Tool", "3": "Precise", "4": "Calibrator", "5": "Metrologist"}},
        {"name": "Experimentation", "icon": "\U0001f9ea", "locked": False, "prereqs": [],
         "levels": {"1": "Mixer", "2": "Hypothesis Maker", "3": "Variable Controller", "4": "Experimenter", "5": "Research Scientist"}},
        {"name": "Documentation", "icon": "\U0001f4d3", "locked": False, "prereqs": [],
         "levels": {"1": "Note Taker", "2": "Logger", "3": "Report Writer", "4": "Paper Author", "5": "Lab Notebook Pro"}},
        {"name": "Chemistry Basics", "icon": "\u2697\ufe0f", "locked": True, "prereqs": [("Measurement", 2), ("Experimentation", 2)],
         "levels": {"1": "Reaction Observer", "2": "pH Tester", "3": "Titrator", "4": "Synthesizer", "5": "Bench Chemist"}},
    ],
}

BADGES = [
    # Getting Started
    {"name": "First Clock-In", "desc": "Clock in for the first time", "icon": "\u23f0", "type": "first_clock_in", "value": {}, "rarity": "common", "xp": 10},
    {"name": "First Project", "desc": "Complete your first project", "icon": "\u2b50", "type": "first_project", "value": {}, "rarity": "common", "xp": 25},
    {"name": "Workshop Regular", "desc": "Work 5 different days", "icon": "\U0001f4c5", "type": "days_worked", "value": {"count": 5}, "rarity": "common", "xp": 15},
    # Time Milestones
    {"name": "10-Hour Club", "desc": "Log 10 approved hours", "icon": "\U0001f55a", "type": "hours_worked", "value": {"hours": 10}, "rarity": "uncommon", "xp": 25},
    {"name": "25-Hour Club", "desc": "Log 25 approved hours", "icon": "\U0001f55b", "type": "hours_worked", "value": {"hours": 25}, "rarity": "rare", "xp": 50},
    {"name": "50-Hour Club", "desc": "Log 50 approved hours", "icon": "\U0001f550", "type": "hours_worked", "value": {"hours": 50}, "rarity": "rare", "xp": 75},
    {"name": "Century Worker", "desc": "Log 100 approved hours", "icon": "\U0001f4af", "type": "hours_worked", "value": {"hours": 100}, "rarity": "epic", "xp": 150},
    {"name": "Marathon Day", "desc": "Work 4+ hours in a single day", "icon": "\U0001f3c3", "type": "hours_in_day", "value": {"hours": 4}, "rarity": "uncommon", "xp": 20},
    # Project Milestones
    {"name": "Hat Trick", "desc": "Complete 3 projects", "icon": "\U0001f3a9", "type": "projects_completed", "value": {"count": 3}, "rarity": "uncommon", "xp": 30},
    {"name": "High Five", "desc": "Complete 5 projects", "icon": "\U0001f64c", "type": "projects_completed", "value": {"count": 5}, "rarity": "rare", "xp": 50},
    {"name": "Perfect 10", "desc": "Complete 10 projects", "icon": "\U0001f3c6", "type": "projects_completed", "value": {"count": 10}, "rarity": "epic", "xp": 100},
    {"name": "Diversified", "desc": "Complete projects in 3+ categories", "icon": "\U0001f310", "type": "category_projects", "value": {"categories": 3}, "rarity": "uncommon", "xp": 30},
    {"name": "Specialist", "desc": "Complete 3 projects in the same category", "icon": "\U0001f3af", "type": "category_projects", "value": {"count": 3, "category": "any"}, "rarity": "uncommon", "xp": 30},
    # Skill & Quality
    {"name": "Level Up", "desc": "Reach Level 2 in any skill", "icon": "\u2b06\ufe0f", "type": "skill_level_reached", "value": {"level": 2, "count": 1}, "rarity": "common", "xp": 15},
    {"name": "Triple Threat", "desc": "Reach Level 2 in 3 different skills", "icon": "\U0001f4aa", "type": "skill_level_reached", "value": {"level": 2, "count": 3}, "rarity": "uncommon", "xp": 30},
    {"name": "Under Budget", "desc": "Complete a project under materials budget", "icon": "\U0001f4b0", "type": "materials_under_budget", "value": {}, "rarity": "uncommon", "xp": 25},
    {"name": "Perfect Timecard", "desc": "Have a timecard approved with zero edits", "icon": "\u2705", "type": "perfect_timecard", "value": {}, "rarity": "uncommon", "xp": 20},
    {"name": "Streak Week", "desc": "Work 7 consecutive days", "icon": "\U0001f525", "type": "streak_days", "value": {"days": 7}, "rarity": "rare", "xp": 50},
    # Rare / Fun
    {"name": "Night Owl", "desc": "Clock in before 8 AM", "icon": "\U0001f989", "type": "first_clock_in", "value": {}, "rarity": "rare", "xp": 15},
    {"name": "Documentarian", "desc": "Upload 10+ photos across projects", "icon": "\U0001f4f8", "type": "photos_uploaded", "value": {"count": 10}, "rarity": "uncommon", "xp": 20},
    {"name": "Speed Runner", "desc": "Complete a project in under 3 days", "icon": "\u26a1", "type": "projects_completed", "value": {"count": 1}, "rarity": "rare", "xp": 40},
    {"name": "Master Craftsman", "desc": "Reach Level 5 in any skill", "icon": "\U0001f451", "type": "skill_level_reached", "value": {"level": 5, "count": 1}, "rarity": "legendary", "xp": 200},
    {"name": "Summer Champion", "desc": "Earn $500+ total", "icon": "\U0001f3c6", "type": "total_earned", "value": {"amount": 500}, "rarity": "legendary", "xp": 250},
    # Skill Tree Badges
    {"name": "Key Turner", "desc": "Unlock your first locked skill", "icon": "\U0001f511", "type": "skills_unlocked", "value": {"count": 1}, "rarity": "uncommon", "xp": 15},
    {"name": "Lockpicker", "desc": "Unlock 5 locked skills", "icon": "\U0001f510", "type": "skills_unlocked", "value": {"count": 5}, "rarity": "rare", "xp": 40},
    {"name": "Skeleton Key", "desc": "Unlock 15 locked skills", "icon": "\U0001f5dd\ufe0f", "type": "skills_unlocked", "value": {"count": 15}, "rarity": "epic", "xp": 100},
    {"name": "Deep Dive", "desc": "Reach Level 4 in any single skill", "icon": "\U0001f4a0", "type": "skill_level_reached", "value": {"level": 4, "count": 1}, "rarity": "rare", "xp": 50},
    {"name": "Mastery", "desc": "Reach Level 5 in any single skill", "icon": "\U0001f48e", "type": "skill_level_reached", "value": {"level": 5, "count": 1}, "rarity": "epic", "xp": 100},
    {"name": "Double Mastery", "desc": "Reach Level 5 in two skills", "icon": "\U0001f48e\U0001f48e", "type": "skill_level_reached", "value": {"level": 5, "count": 2}, "rarity": "epic", "xp": 150},
    {"name": "Grandmaster", "desc": "Reach Level 5 in five skills", "icon": "\U0001f451\U0001f451", "type": "skill_level_reached", "value": {"level": 5, "count": 5}, "rarity": "legendary", "xp": 300},
    {"name": "Renaissance Kid", "desc": "Have Level 1+ in skills across 4 categories", "icon": "\U0001f3ad", "type": "skill_categories_breadth", "value": {"min_level": 1, "categories": 4}, "rarity": "uncommon", "xp": 25},
    {"name": "Polymath", "desc": "Have Level 2+ in skills across 6 categories", "icon": "\U0001f4da", "type": "skill_categories_breadth", "value": {"min_level": 2, "categories": 6}, "rarity": "rare", "xp": 75},
    {"name": "Universal Genius", "desc": "Have Level 3+ in skills across all categories", "icon": "\U0001f30d", "type": "skill_categories_breadth", "value": {"min_level": 3, "categories": 8}, "rarity": "legendary", "xp": 500},
    {"name": "Bridge Builder", "desc": "Unlock a skill that required a prerequisite from another category", "icon": "\U0001f309", "type": "cross_category_unlock", "value": {}, "rarity": "rare", "xp": 40},
]

SAMPLE_PROJECTS = [
    {
        "title": "Build a Birdhouse",
        "description": "Build a classic wooden birdhouse from pine boards. Follow the Instructables guide for measurements and assembly.",
        "instructables_url": "https://www.instructables.com/Simple-Birdhouse-1/",
        "category": "Woodworking",
        "difficulty": 2,
        "bonus_amount": "15.00",
        "materials_budget": "25.00",
        "milestones": [
            {"title": "Gather materials and tools", "order": 1},
            {"title": "Measure and cut all pieces", "order": 2},
            {"title": "Assemble the walls and floor", "order": 3},
            {"title": "Attach the roof", "order": 4},
            {"title": "Sand and finish", "order": 5},
        ],
        "materials": [
            {"name": "Pine board (1x6x6ft)", "estimated_cost": "8.00"},
            {"name": "Wood screws (#6 x 1.5in)", "estimated_cost": "4.00"},
            {"name": "Wood glue", "estimated_cost": "5.00"},
            {"name": "Sandpaper (120 & 220 grit)", "estimated_cost": "3.00"},
            {"name": "Exterior paint or stain", "estimated_cost": "5.00"},
        ],
        "skills": [("Measuring & Marking", 1), ("Hand Tools", 2), ("Sanding & Finishing", 1)],
    },
    {
        "title": "LED Mood Lamp",
        "description": "Create an RGB LED mood lamp with an Arduino and 3D-printed enclosure. Changes colors based on time of day.",
        "category": "Electronics",
        "difficulty": 3,
        "bonus_amount": "25.00",
        "materials_budget": "35.00",
        "milestones": [
            {"title": "Wire the LED circuit on breadboard", "order": 1},
            {"title": "Program the Arduino color cycles", "order": 2},
            {"title": "Design the lamp enclosure", "order": 3},
            {"title": "Solder permanent connections", "order": 4},
            {"title": "Final assembly and testing", "order": 5},
        ],
        "materials": [
            {"name": "Arduino Nano", "estimated_cost": "12.00"},
            {"name": "NeoPixel LED ring (16 LEDs)", "estimated_cost": "8.00"},
            {"name": "Breadboard + jumper wires", "estimated_cost": "5.00"},
            {"name": "USB cable", "estimated_cost": "3.00"},
            {"name": "Diffuser material", "estimated_cost": "4.00"},
        ],
        "skills": [("Wiring & Connectors", 1), ("Through-Hole Soldering", 2), ("Microcontrollers", 1)],
    },
    {
        "title": "Summer Cookbook",
        "description": "Create a personal cookbook with 10 original summer recipes. Each recipe includes photos, ingredients, and step-by-step instructions.",
        "category": "Cooking",
        "difficulty": 2,
        "bonus_amount": "20.00",
        "materials_budget": "50.00",
        "milestones": [
            {"title": "Plan 10 recipes and shopping lists", "order": 1},
            {"title": "Cook and photograph first 3 recipes", "order": 2},
            {"title": "Cook and photograph next 4 recipes", "order": 3},
            {"title": "Cook and photograph final 3 recipes", "order": 4},
            {"title": "Compile and design the cookbook", "order": 5},
        ],
        "materials": [
            {"name": "Recipe binder and page protectors", "estimated_cost": "12.00"},
            {"name": "Groceries for recipes", "estimated_cost": "30.00"},
            {"name": "Printed recipe cards", "estimated_cost": "8.00"},
        ],
        "skills": [("Knife Skills", 1), ("Heat Control", 1), ("Flavor & Seasoning", 1), ("Food Safety", 1)],
    },
]


class Command(BaseCommand):
    help = "Seed the database with initial data"

    def add_arguments(self, parser):
        parser.add_argument("--noinput", action="store_true", help="Skip confirmation")

    def handle(self, *args, **options):
        if not options["noinput"]:
            confirm = input("This will seed the database. Continue? [y/N] ")
            if confirm.lower() != "y":
                self.stdout.write("Cancelled.")
                return

        self._create_users()
        categories = self._create_categories()
        skill_map = self._create_skills(categories)
        self._create_prerequisites(skill_map)
        self._create_badges()
        self._create_sample_projects(categories, skill_map)
        self._create_sample_chores()
        self._create_sample_homework()
        self._create_pet_species()
        self._create_item_catalog()
        self._create_sample_habits()
        self._create_sample_quests()

        self.stdout.write(self.style.SUCCESS("Seeding complete!"))

    def _create_users(self):
        from apps.projects.models import User

        parent_pw = os.environ.get("PARENT_PASSWORD", "summerforge2025")
        child_pw = os.environ.get("CHILD_PASSWORD", "summerforge2025")

        parent, created = User.objects.get_or_create(
            username="dad",
            defaults={"display_name": "Dad", "role": "parent", "is_staff": True},
        )
        if created:
            parent.set_password(parent_pw)
            parent.save()
            self.stdout.write(f"  Created parent: {parent.username}")
        else:
            self.stdout.write(f"  Parent already exists: {parent.username}")

        child, created = User.objects.get_or_create(
            username="abby",
            defaults={"display_name": "Abby", "role": "child", "hourly_rate": Decimal("8.00")},
        )
        if created:
            child.set_password(child_pw)
            child.save()
            self.stdout.write(f"  Created child: {child.username}")
        else:
            self.stdout.write(f"  Child already exists: {child.username}")

    def _create_categories(self):
        from apps.projects.models import SkillCategory

        categories = {}
        for cat_data in SKILL_CATEGORIES:
            cat, created = SkillCategory.objects.get_or_create(
                name=cat_data["name"],
                defaults={
                    "icon": cat_data["icon"],
                    "color": cat_data["color"],
                    "description": cat_data["description"],
                },
            )
            categories[cat.name] = cat
            if created:
                self.stdout.write(f"  Created category: {cat.name}")
        return categories

    def _create_skills(self, categories):
        from apps.achievements.models import Skill

        skill_map = {}
        for cat_name, skills in SKILLS_BY_CATEGORY.items():
            category = categories[cat_name]
            for i, skill_data in enumerate(skills):
                skill, created = Skill.objects.get_or_create(
                    name=skill_data["name"],
                    category=category,
                    defaults={
                        "icon": skill_data["icon"],
                        "is_locked_by_default": skill_data["locked"],
                        "level_names": skill_data["levels"],
                        "order": i,
                    },
                )
                key = f"{cat_name}::{skill_data['name']}"
                skill_map[key] = skill
                # Also store without category prefix for same-category lookups
                skill_map[skill_data["name"]] = skill
                if created:
                    self.stdout.write(f"  Created skill: {cat_name} > {skill.name}")
        return skill_map

    def _create_prerequisites(self, skill_map):
        from apps.achievements.models import SkillPrerequisite

        count = 0
        for cat_name, skills in SKILLS_BY_CATEGORY.items():
            for skill_data in skills:
                if not skill_data["prereqs"]:
                    continue
                skill_key = f"{cat_name}::{skill_data['name']}"
                skill = skill_map[skill_key]
                for prereq_name, level in skill_data["prereqs"]:
                    # Handle cross-category prereqs (prefixed with "Category::")
                    if "::" in prereq_name:
                        req_skill = skill_map.get(prereq_name)
                    else:
                        req_skill = skill_map.get(f"{cat_name}::{prereq_name}")
                    if not req_skill:
                        self.stdout.write(
                            self.style.WARNING(f"  Prereq not found: {prereq_name} for {skill.name}")
                        )
                        continue
                    _, created = SkillPrerequisite.objects.get_or_create(
                        skill=skill,
                        required_skill=req_skill,
                        defaults={"required_level": level},
                    )
                    if created:
                        count += 1
        self.stdout.write(f"  Created {count} skill prerequisites")

    def _create_badges(self):
        from apps.achievements.models import Badge

        count = 0
        for b in BADGES:
            _, created = Badge.objects.get_or_create(
                name=b["name"],
                defaults={
                    "description": b["desc"],
                    "icon": b["icon"],
                    "criteria_type": b["type"],
                    "criteria_value": b["value"],
                    "xp_bonus": b["xp"],
                    "rarity": b["rarity"],
                },
            )
            if created:
                count += 1
        self.stdout.write(f"  Created {count} badges")

    def _create_sample_projects(self, categories, skill_map):
        from apps.projects.models import MaterialItem, Project, ProjectMilestone, User
        from apps.achievements.models import ProjectSkillTag

        try:
            parent = User.objects.get(username="dad")
            child = User.objects.get(username="abby")
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING("  Users not found, skipping projects"))
            return

        for proj_data in SAMPLE_PROJECTS:
            category = categories.get(proj_data["category"])
            project, created = Project.objects.get_or_create(
                title=proj_data["title"],
                created_by=parent,
                defaults={
                    "description": proj_data["description"],
                    "instructables_url": proj_data.get("instructables_url"),
                    "category": category,
                    "difficulty": proj_data["difficulty"],
                    "bonus_amount": Decimal(proj_data["bonus_amount"]),
                    "materials_budget": Decimal(proj_data["materials_budget"]),
                    "assigned_to": child,
                    "status": "active",
                },
            )
            if not created:
                continue

            self.stdout.write(f"  Created project: {project.title}")

            for ms in proj_data["milestones"]:
                ProjectMilestone.objects.create(
                    project=project, title=ms["title"], order=ms["order"],
                )

            for mat in proj_data["materials"]:
                MaterialItem.objects.create(
                    project=project,
                    name=mat["name"],
                    estimated_cost=Decimal(mat["estimated_cost"]),
                )

            for skill_name, weight in proj_data.get("skills", []):
                cat_name = proj_data["category"]
                skill = skill_map.get(f"{cat_name}::{skill_name}")
                if skill:
                    ProjectSkillTag.objects.get_or_create(
                        project=project, skill=skill,
                        defaults={"xp_weight": weight},
                    )

    def _create_sample_chores(self):
        from apps.chores.models import Chore
        from apps.projects.models import User
        from datetime import date

        parent = User.objects.filter(role="parent").first()
        child = User.objects.filter(role="child").first()
        if not parent:
            return

        today = date.today()

        SAMPLE_CHORES = [
            {"title": "Wash Dishes", "icon": "\U0001f37d\ufe0f", "description": "Wash, dry, and put away all dishes from the sink.",
             "reward_amount": "1.00", "coin_reward": 2, "recurrence": "daily",
             "week_schedule": "every_week"},
            {"title": "Clean Room", "icon": "\U0001f9f9", "description": "Make bed, pick up floor, organize desk.",
             "reward_amount": "1.50", "coin_reward": 3, "recurrence": "daily",
             "week_schedule": "every_week"},
            {"title": "Take Out Trash", "icon": "\U0001f5d1\ufe0f", "description": "Empty all trash cans and replace bags. Take bins to curb on collection day.",
             "reward_amount": "0.75", "coin_reward": 1, "recurrence": "daily",
             "week_schedule": "every_week"},
            {"title": "Feed Pets", "icon": "\U0001f43e", "description": "Fresh food and water for all pets.",
             "reward_amount": "0.50", "coin_reward": 1, "recurrence": "daily",
             "week_schedule": "alternating", "schedule_start_date": today},
            {"title": "Vacuum Common Areas", "icon": "\U0001f3e0", "description": "Vacuum living room, hallway, and stairs.",
             "reward_amount": "2.00", "coin_reward": 3, "recurrence": "weekly",
             "week_schedule": "every_week"},
            {"title": "Mow the Lawn", "icon": "\U0001f33f", "description": "Mow front and back yard, edge sidewalks.",
             "reward_amount": "5.00", "coin_reward": 5, "recurrence": "weekly",
             "week_schedule": "every_week"},
            {"title": "Organize Garage Workbench", "icon": "\U0001f527", "description": "Clean up the workbench, return all tools to their places, sweep the floor.",
             "reward_amount": "3.00", "coin_reward": 5, "recurrence": "one_time",
             "week_schedule": "every_week"},
        ]

        for i, chore_data in enumerate(SAMPLE_CHORES):
            chore, created = Chore.objects.get_or_create(
                title=chore_data["title"],
                defaults={
                    "description": chore_data["description"],
                    "icon": chore_data["icon"],
                    "reward_amount": Decimal(chore_data["reward_amount"]),
                    "coin_reward": chore_data["coin_reward"],
                    "recurrence": chore_data["recurrence"],
                    "week_schedule": chore_data["week_schedule"],
                    "schedule_start_date": chore_data.get("schedule_start_date"),
                    "assigned_to": child,
                    "created_by": parent,
                    "order": i,
                },
            )
            if created:
                self.stdout.write(f"  Created chore: {chore.title}")

    def _create_sample_homework(self):
        from datetime import timedelta

        from apps.homework.models import HomeworkAssignment, HomeworkTemplate
        from apps.projects.models import User

        parent = User.objects.filter(role="parent").first()
        child = User.objects.filter(role="child").first()
        if not parent or not child:
            return

        from django.utils import timezone

        today = timezone.localdate()

        SAMPLE_HOMEWORK = [
            {
                "title": "Math Worksheet Ch. 7",
                "subject": "math",
                "effort_level": 2,
                "due_date": today + timedelta(days=1),
                "reward_amount": "2.00",
                "coin_reward": 5,
            },
            {
                "title": "Read 'Hatchet' Chapters 4-6",
                "subject": "reading",
                "effort_level": 3,
                "due_date": today + timedelta(days=2),
                "reward_amount": "3.00",
                "coin_reward": 8,
            },
            {
                "title": "Science Lab Report: Plant Growth",
                "description": "Write up observations from the bean plant experiment.",
                "subject": "science",
                "effort_level": 4,
                "due_date": today + timedelta(days=5),
                "reward_amount": "5.00",
                "coin_reward": 15,
            },
            {
                "title": "Spelling Practice Words",
                "subject": "writing",
                "effort_level": 1,
                "due_date": today,
                "reward_amount": "1.00",
                "coin_reward": 3,
            },
            {
                "title": "Social Studies Map Activity",
                "subject": "social_studies",
                "effort_level": 3,
                "due_date": today + timedelta(days=3),
                "reward_amount": "3.00",
                "coin_reward": 8,
            },
        ]

        for hw in SAMPLE_HOMEWORK:
            _, created = HomeworkAssignment.objects.get_or_create(
                title=hw["title"],
                assigned_to=child,
                defaults={
                    "description": hw.get("description", ""),
                    "subject": hw["subject"],
                    "effort_level": hw["effort_level"],
                    "due_date": hw["due_date"],
                    "created_by": parent,
                    "reward_amount": Decimal(hw["reward_amount"]),
                    "coin_reward": hw["coin_reward"],
                },
            )
            if created:
                self.stdout.write(f"  Created homework: {hw['title']}")

        # Create a template.
        _, created = HomeworkTemplate.objects.get_or_create(
            title="Weekly Reading Assignment",
            defaults={
                "description": "Read assigned chapters and write a brief summary.",
                "subject": "reading",
                "effort_level": 3,
                "reward_amount": Decimal("3.00"),
                "coin_reward": 8,
                "created_by": parent,
            },
        )
        if created:
            self.stdout.write("  Created homework template: Weekly Reading Assignment")

    def _create_pet_species(self):
        from apps.pets.models import PetSpecies, PotionType

        species_data = [
            {"name": "Wolf", "icon": "🐺", "description": "A loyal pack hunter", "food_preference": "meat"},
            {"name": "Dragon", "icon": "🐉", "description": "A fierce fire-breather", "food_preference": "fish"},
            {"name": "Fox", "icon": "🦊", "description": "A clever forest dweller", "food_preference": "berries"},
            {"name": "Owl", "icon": "🦉", "description": "A wise night hunter", "food_preference": "seeds"},
            {"name": "Cat", "icon": "🐱", "description": "A graceful companion", "food_preference": "fish"},
            {"name": "Bear", "icon": "🐻", "description": "A powerful protector", "food_preference": "honey"},
            {"name": "Phoenix", "icon": "🔥", "description": "A legendary fire bird", "food_preference": "cake"},
            {"name": "Unicorn", "icon": "🦄", "description": "A magical horned steed", "food_preference": "candy"},
        ]

        for data in species_data:
            species, created = PetSpecies.objects.get_or_create(
                name=data["name"], defaults=data,
            )
            if created:
                self.stdout.write(f"  Created pet species: {species.name}")

        potion_data = [
            {"name": "Base", "color_hex": "#8B7355", "rarity": "common", "description": "Natural colors"},
            {"name": "Fire", "color_hex": "#FF4500", "rarity": "uncommon", "description": "Red/orange tones"},
            {"name": "Ice", "color_hex": "#87CEEB", "rarity": "uncommon", "description": "Blue/white tones"},
            {"name": "Shadow", "color_hex": "#4B0082", "rarity": "rare", "description": "Dark/purple tones"},
            {"name": "Golden", "color_hex": "#FFD700", "rarity": "epic", "description": "Gold/glowing"},
            {"name": "Cosmic", "color_hex": "#191970", "rarity": "legendary", "description": "Starfield/nebula"},
        ]

        for data in potion_data:
            potion, created = PotionType.objects.get_or_create(
                name=data["name"], defaults=data,
            )
            if created:
                self.stdout.write(f"  Created potion type: {potion.name}")

    def _create_item_catalog(self):
        from apps.rpg.models import ItemDefinition, DropTable

        items_data = [
            # Pet Eggs (for Phase 3 - pets system)
            {"name": "Wolf Egg", "icon": "🥚", "item_type": "egg", "rarity": "common", "coin_value": 3, "metadata": {"species": "wolf"}},
            {"name": "Dragon Egg", "icon": "🥚", "item_type": "egg", "rarity": "uncommon", "coin_value": 5, "metadata": {"species": "dragon"}},
            {"name": "Fox Egg", "icon": "🥚", "item_type": "egg", "rarity": "common", "coin_value": 3, "metadata": {"species": "fox"}},
            {"name": "Owl Egg", "icon": "🥚", "item_type": "egg", "rarity": "common", "coin_value": 3, "metadata": {"species": "owl"}},
            {"name": "Cat Egg", "icon": "🥚", "item_type": "egg", "rarity": "common", "coin_value": 3, "metadata": {"species": "cat"}},
            {"name": "Bear Egg", "icon": "🥚", "item_type": "egg", "rarity": "uncommon", "coin_value": 5, "metadata": {"species": "bear"}},
            {"name": "Phoenix Egg", "icon": "🥚", "item_type": "egg", "rarity": "rare", "coin_value": 10, "metadata": {"species": "phoenix"}},
            {"name": "Unicorn Egg", "icon": "🥚", "item_type": "egg", "rarity": "rare", "coin_value": 10, "metadata": {"species": "unicorn"}},
            # Hatching Potions
            {"name": "Base Potion", "icon": "🧪", "item_type": "potion", "rarity": "common", "coin_value": 2, "metadata": {"variant": "base", "color": "#8B7355"}},
            {"name": "Fire Potion", "icon": "🧪", "item_type": "potion", "rarity": "uncommon", "coin_value": 5, "metadata": {"variant": "fire", "color": "#FF4500"}},
            {"name": "Ice Potion", "icon": "🧪", "item_type": "potion", "rarity": "uncommon", "coin_value": 5, "metadata": {"variant": "ice", "color": "#87CEEB"}},
            {"name": "Shadow Potion", "icon": "🧪", "item_type": "potion", "rarity": "rare", "coin_value": 10, "metadata": {"variant": "shadow", "color": "#4B0082"}},
            {"name": "Golden Potion", "icon": "🧪", "item_type": "potion", "rarity": "epic", "coin_value": 25, "metadata": {"variant": "golden", "color": "#FFD700"}},
            {"name": "Cosmic Potion", "icon": "🧪", "item_type": "potion", "rarity": "legendary", "coin_value": 50, "metadata": {"variant": "cosmic", "color": "#191970"}},
            # Pet Food
            {"name": "Meat", "icon": "🥩", "item_type": "food", "rarity": "common", "coin_value": 1, "metadata": {"food_type": "meat", "growth": 5}},
            {"name": "Fish", "icon": "🐟", "item_type": "food", "rarity": "common", "coin_value": 1, "metadata": {"food_type": "fish", "growth": 5}},
            {"name": "Berries", "icon": "🫐", "item_type": "food", "rarity": "common", "coin_value": 1, "metadata": {"food_type": "berries", "growth": 5}},
            {"name": "Seeds", "icon": "🌻", "item_type": "food", "rarity": "common", "coin_value": 1, "metadata": {"food_type": "seeds", "growth": 5}},
            {"name": "Honey", "icon": "🍯", "item_type": "food", "rarity": "uncommon", "coin_value": 2, "metadata": {"food_type": "honey", "growth": 8}},
            {"name": "Cake", "icon": "🎂", "item_type": "food", "rarity": "uncommon", "coin_value": 2, "metadata": {"food_type": "cake", "growth": 8}},
            # Coin Pouches
            {"name": "Small Coin Pouch", "icon": "👛", "item_type": "coin_pouch", "rarity": "common", "coin_value": 5, "metadata": {"coins": 5}},
            {"name": "Medium Coin Pouch", "icon": "💰", "item_type": "coin_pouch", "rarity": "uncommon", "coin_value": 15, "metadata": {"coins": 15}},
            {"name": "Large Coin Pouch", "icon": "💎", "item_type": "coin_pouch", "rarity": "rare", "coin_value": 50, "metadata": {"coins": 50}},
        ]

        item_map = {}
        for data in items_data:
            item, created = ItemDefinition.objects.get_or_create(
                name=data["name"],
                defaults=data,
            )
            item_map[item.name] = item
            if created:
                self.stdout.write(f"  Created item: {item.name}")

        # Drop table entries for common triggers
        common_triggers = ["clock_out", "chore_complete", "homework_complete", "milestone_complete", "habit_log"]

        # Eggs drop from all triggers (weight by rarity)
        egg_weights = {"common": 10, "uncommon": 5, "rare": 2, "epic": 1, "legendary": 1}
        for trigger in common_triggers:
            for item in ItemDefinition.objects.filter(item_type="egg"):
                w = egg_weights.get(item.rarity, 1)
                DropTable.objects.get_or_create(
                    trigger_type=trigger, item=item,
                    defaults={"weight": w},
                )

            # Potions
            for item in ItemDefinition.objects.filter(item_type="potion"):
                w = egg_weights.get(item.rarity, 1)
                DropTable.objects.get_or_create(
                    trigger_type=trigger, item=item,
                    defaults={"weight": w},
                )

            # Food (higher weight - more common drops)
            for item in ItemDefinition.objects.filter(item_type="food"):
                DropTable.objects.get_or_create(
                    trigger_type=trigger, item=item,
                    defaults={"weight": 15},
                )

            # Coin pouches
            for item in ItemDefinition.objects.filter(item_type="coin_pouch"):
                w = egg_weights.get(item.rarity, 1) * 2
                DropTable.objects.get_or_create(
                    trigger_type=trigger, item=item,
                    defaults={"weight": w},
                )

        self.stdout.write(self.style.SUCCESS(f"  Created {len(items_data)} items and drop table entries"))

    def _create_sample_habits(self):
        from apps.rpg.models import CharacterProfile, Habit
        from apps.projects.models import User

        parent = User.objects.filter(role="parent").first()
        child = User.objects.filter(role="child").first()
        if not parent or not child:
            self.stdout.write("  Skipping habits: no parent/child found")
            return

        CharacterProfile.objects.get_or_create(user=child)

        habits = [
            {"name": "Read for 15 min", "icon": "\U0001f4d6", "habit_type": "positive", "coin_reward": 2, "xp_reward": 10},
            {"name": "Practice instrument", "icon": "\U0001f3b5", "habit_type": "positive", "coin_reward": 2, "xp_reward": 10},
            {"name": "Drink water", "icon": "\U0001f4a7", "habit_type": "positive", "coin_reward": 1, "xp_reward": 5},
            {"name": "Exercise / stretch", "icon": "\U0001f3c3", "habit_type": "positive", "coin_reward": 1, "xp_reward": 5},
            {"name": "Screen time snack", "icon": "\U0001f36b", "habit_type": "negative", "coin_reward": 0, "xp_reward": 0},
        ]

        for h_data in habits:
            habit, created = Habit.objects.get_or_create(
                name=h_data["name"],
                user=child,
                defaults={**h_data, "created_by": parent},
            )
            if created:
                self.stdout.write(f"  Created habit: {habit.name}")

    def _create_sample_quests(self):
        from apps.quests.models import QuestDefinition, QuestRewardItem
        from apps.rpg.models import ItemDefinition

        quests = [
            {
                "name": "Dragon Slayer",
                "description": "Deal 500 damage to the mighty dragon by completing tasks!",
                "icon": "\U0001f409",
                "quest_type": "boss",
                "target_value": 500,
                "duration_days": 7,
                "coin_reward": 50,
                "xp_reward": 100,
                "is_system": True,
            },
            {
                "name": "Feather Collector",
                "description": "Collect 10 phoenix feathers by completing any tasks.",
                "icon": "\U0001fab6",
                "quest_type": "collection",
                "target_value": 10,
                "duration_days": 5,
                "coin_reward": 25,
                "xp_reward": 50,
                "is_system": True,
            },
            {
                "name": "Chore Champion",
                "description": "Complete 15 chores to prove your household mastery!",
                "icon": "\U0001f3c6",
                "quest_type": "collection",
                "target_value": 15,
                "duration_days": 7,
                "coin_reward": 30,
                "xp_reward": 75,
                "is_system": True,
                "trigger_filter": {"allowed_triggers": ["chore_complete"]},
            },
            {
                "name": "Focus Master",
                "description": "Clock 20 hours of focused project work to defeat the distraction monster!",
                "icon": "\U0001f9e0",
                "quest_type": "boss",
                "target_value": 200,
                "duration_days": 14,
                "coin_reward": 75,
                "xp_reward": 150,
                "is_system": True,
                "trigger_filter": {"allowed_triggers": ["clock_out"]},
            },
        ]

        for q_data in quests:
            trigger_filter = q_data.pop("trigger_filter", {})
            qd, created = QuestDefinition.objects.get_or_create(
                name=q_data["name"],
                defaults={**q_data, "trigger_filter": trigger_filter},
            )
            if created:
                self.stdout.write(f"  Created quest: {qd.name}")
                # Add egg reward to boss quests
                if qd.quest_type == "boss":
                    egg = ItemDefinition.objects.filter(item_type="egg").first()
                    if egg:
                        QuestRewardItem.objects.get_or_create(
                            quest_definition=qd, item=egg, defaults={"quantity": 1},
                        )
