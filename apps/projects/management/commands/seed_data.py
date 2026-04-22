import os
from decimal import Decimal

from django.core.management.base import BaseCommand


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
        # The RPG/skill-tree catalog (categories, skills, prereqs, badges,
        # pet species, potions, items, drops, quests) is authored in
        # content/rpg/initial/*.yaml and loaded here. Editing YAML is the
        # single source of truth — don't add inline Python lists for new
        # content, add an entry to the matching pack file.
        from django.core.management import call_command
        call_command("loadrpgcontent", verbosity=options.get("verbosity", 1))

        # Fixture-style sample data (projects, chores, homework, habits)
        # stays inline because it depends on the seeded users.
        categories = self._resolve_categories()
        skill_map = self._resolve_skill_map()
        self._create_sample_projects(categories, skill_map)
        self._create_sample_chores()
        self._create_sample_homework()
        self._create_sample_habits()
        self._create_sample_savings_goals()

        self.stdout.write(self.style.SUCCESS("Seeding complete!"))

    def _resolve_categories(self):
        from apps.achievements.models import SkillCategory
        return {c.name: c for c in SkillCategory.objects.all()}

    def _resolve_skill_map(self):
        from apps.achievements.models import Skill
        skill_map = {}
        for skill in Skill.objects.select_related("category").all():
            skill_map[f"{skill.category.name}::{skill.name}"] = skill
            skill_map[skill.name] = skill
        return skill_map

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
            },
            {
                "title": "Read 'Hatchet' Chapters 4-6",
                "subject": "reading",
                "effort_level": 3,
                "due_date": today + timedelta(days=2),
            },
            {
                "title": "Science Lab Report: Plant Growth",
                "description": "Write up observations from the bean plant experiment.",
                "subject": "science",
                "effort_level": 4,
                "due_date": today + timedelta(days=5),
            },
            {
                "title": "Spelling Practice Words",
                "subject": "writing",
                "effort_level": 1,
                "due_date": today,
            },
            {
                "title": "Social Studies Map Activity",
                "subject": "social_studies",
                "effort_level": 3,
                "due_date": today + timedelta(days=3),
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
                "created_by": parent,
            },
        )
        if created:
            self.stdout.write("  Created homework template: Weekly Reading Assignment")

    def _create_sample_habits(self):
        from apps.habits.models import Habit
        from apps.projects.models import User
        from apps.rpg.models import CharacterProfile

        parent = User.objects.filter(role="parent").first()
        child = User.objects.filter(role="child").first()
        if not parent or not child:
            self.stdout.write("  Skipping habits: no parent/child found")
            return

        CharacterProfile.objects.get_or_create(user=child)

        habits = [
            {"name": "Read for 15 min", "icon": "\U0001f4d6", "habit_type": "positive", "xp_reward": 10, "max_taps_per_day": 1},
            {"name": "Practice instrument", "icon": "\U0001f3b5", "habit_type": "positive", "xp_reward": 10, "max_taps_per_day": 1},
            {"name": "Drink water", "icon": "\U0001f4a7", "habit_type": "positive", "xp_reward": 5, "max_taps_per_day": 8},
            {"name": "Brush teeth", "icon": "\U0001fa74", "habit_type": "positive", "xp_reward": 5, "max_taps_per_day": 2},
            {"name": "Exercise / stretch", "icon": "\U0001f3c3", "habit_type": "positive", "xp_reward": 5, "max_taps_per_day": 1},
            {"name": "Screen time snack", "icon": "\U0001f36b", "habit_type": "negative", "xp_reward": 0, "max_taps_per_day": 1},
        ]

        for h_data in habits:
            habit, created = Habit.objects.get_or_create(
                name=h_data["name"],
                user=child,
                defaults={**h_data, "created_by": parent},
            )
            if created:
                self.stdout.write(f"  Created habit: {habit.name}")

    def _create_sample_savings_goals(self):
        """Seed a mix of in-progress + completed sample goals per child.

        ``current_amount`` is derived from ``PaymentService.get_balance``
        at read time, so we don't — and can't — seed a stored amount.
        The in-progress goal's visible progress will depend on whatever
        balance the child accumulates through other seeded activity; for
        a freshly seeded DB the balance is $0, which correctly renders
        "$0 / $50" on the Hoards tab.
        """
        from apps.projects.models import SavingsGoal, User
        from django.utils import timezone
        from datetime import timedelta

        for child in User.objects.filter(role="child"):
            SavingsGoal.objects.get_or_create(
                user=child,
                title="Lego Set",
                defaults={
                    "target_amount": Decimal("50.00"),
                    "icon": "🧱",
                },
            )
            completed, created = SavingsGoal.objects.get_or_create(
                user=child,
                title="Headphones",
                defaults={
                    "target_amount": Decimal("25.00"),
                    "icon": "🎧",
                    "is_completed": True,
                    "completed_at": timezone.now() - timedelta(days=5),
                },
            )
            if created:
                self.stdout.write(f"  Created sample savings goals for {child.username}")

