"""Edition facts checked against linked publishers on 2026-10-17.

Page counts describe the listed ISBN; formats describe verified editions of the
work, not library stock. Moods, styles and themes are our editorial tags. Series
contains curated reading order where verified, not a claim that null means a
standalone book. No metadata calls, cover downloads or licensed assets live here.
"""


def _details(isbn, page_count, formats, moods, styles, themes, series=None, source_urls=()):
    return {
        "isbn": isbn,
        "page_count": page_count,
        "formats": list(formats),
        "moods": list(moods),
        "styles": list(styles),
        "themes": list(themes),
        "series": {"id": series[0], "title": series[1], "position": series[2]} if series else None,
        "cover_url": f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false" if isbn else "",
        "source_urls": list(source_urls),
    }


# Publisher pages expose these edition details as Book structured data or in
# their product details/format selectors. The Blazewrath publisher article lists
# its print ISBN but no page count, so we leave that count unknown.
CATALOG_DETAILS = {
    'the-princess-in-black': _details(
        '9780763678883', 96, ('print',), ('funny', 'exciting'), ('illustrated', 'short_chapters'), ('magic',)
    ),
    'narwhal-unicorn-of-the-sea': _details(
        '9781101918265', 64, ('print', 'ebook', 'audiobook'), ('funny', 'cozy'), ('graphic_novel', 'short_chapters'), ('animals', 'friendship'),
        series=('narwhal-and-jelly', 'Narwhal and Jelly', 1)
    ),
    'nate-the-great': _details(
        '9780385730174', 64, ('print', 'ebook', 'audiobook'), ('cozy', 'suspenseful'), ('illustrated', 'short_chapters'), ('puzzles', 'friendship')
    ),
    'dinosaurs-before-dark': _details(
        '9780679824114', 80, ('print', 'ebook', 'audiobook'), ('exciting',), ('illustrated', 'short_chapters'), ('animals', 'magic', 'history', 'family'),
        series=('magic-tree-house', 'Magic Tree House', 1)
    ),
    'narwhal-candace-fleming': _details(
        '9780593377789', 48, ('print', 'ebook', 'audiobook'), ('thoughtful', 'cozy'), ('illustrated',), ('animals', 'nature')
    ),
    'the-wild-robot': _details(
        '9780316581097', 320, ('print', 'ebook', 'audiobook'), ('thoughtful', 'exciting'), ('illustrated', 'short_chapters'), ('nature', 'animals', 'family'),
        series=('wild-robot', 'The Wild Robot', 1)
    ),
    'the-lightning-thief': _details(
        '9781368051477', 416, ('print', 'ebook', 'audiobook'), ('exciting', 'funny'), (), ('mythology', 'magic', 'friendship'),
        series=('percy-jackson', 'Percy Jackson and the Olympians', 1)
    ),
    'wonder': _details(
        '9780375869020', 320, ('print', 'ebook', 'audiobook'), ('thoughtful',), (), ('friendship', 'identity', 'family')
    ),
    'the-westing-game': _details(
        '9780593118108', 240, ('print', 'ebook'), ('suspenseful', 'funny'), (), ('puzzles',)
    ),
    'when-you-reach-me': _details(
        '9780375850868', 240, ('print', 'ebook', 'audiobook'), ('suspenseful', 'thoughtful'), (), ('puzzles', 'friendship')
    ),
    'who-was-harriet-tubman': _details(
        '9780593097229', 112, ('print', 'ebook', 'audiobook'), ('thoughtful',), ('illustrated', 'short_chapters'), ('history',)
    ),
    'dragonbreath-1': _details(
        '9780142420959', 160, ('print', 'ebook'), ('funny', 'exciting'), ('illustrated', 'short_chapters'), ('dragons', 'friendship', 'animals')
    ),
    'brown-girl-dreaming': _details(
        '9780147515827', 368, ('print', 'ebook', 'audiobook'), ('thoughtful',), ('verse',), ('history', 'family', 'identity'), source_urls=('https://www.penguinrandomhouse.com/books/304851/brown-girl-dreaming-by-jacqueline-woodson/9780147515827/',)
    ),
    'eragon': _details(
        '9780375890369', 528, ('ebook', 'print', 'audiobook'), ('exciting', 'suspenseful'), (), ('dragons', 'magic', 'friendship'),
        series=('inheritance-cycle', 'The Inheritance Cycle', 1)
    ),
    'the-martian-classroom-edition': _details(
        '9781524763541', 400, ('ebook', 'print'), ('suspenseful', 'funny'), (), ('space', 'inventors')
    ),
    'darius-the-great-is-not-okay': _details(
        '9780525552970', 336, ('print', 'ebook', 'audiobook'), ('thoughtful', 'funny'), (), ('family', 'identity', 'friendship')
    ),
    'seraphina': _details(
        '9780375866227', 528, ('print', 'ebook', 'audiobook'), ('suspenseful', 'thoughtful'), (), ('dragons', 'music', 'identity')
    ),
    'fireborne': _details(
        '9780525518235', 464, ('print', 'ebook', 'audiobook'), ('exciting', 'suspenseful'), (), ('dragons', 'friendship', 'family')
    ),
    'eon': _details(
        '9780142417119', 576, ('print', 'ebook'), ('exciting', 'suspenseful'), (), ('dragons', 'magic', 'identity')
    ),
    'the-hero-and-the-crown': _details(
        '9780441013050', 304, ('print',), ('exciting', 'thoughtful'), (), ('dragons', 'magic', 'identity')
    ),
    'six-of-crows': _details(
        '9781250076960', 496, ('print',), ('suspenseful', 'exciting'), (), ('magic', 'friendship', 'puzzles')
    ),
    'the-cruel-prince': _details(
        '9780316310314', 416, ('print', 'ebook', 'audiobook'), ('suspenseful', 'exciting'), (), ('magic', 'family', 'identity')
    ),
    'carry-on': _details(
        '9781250135025', 528, ('print', 'audiobook'), ('funny', 'suspenseful'), (), ('magic', 'identity', 'friendship')
    ),
    'six-crimson-cranes': _details(
        '9780593300947', 480, ('print', 'ebook', 'audiobook'), ('exciting', 'suspenseful'), (), ('dragons', 'magic', 'family')
    ),
    'the-girl-who-fell-beneath-the-sea': _details(
        '9781250780874', 336, ('ebook',), ('thoughtful', 'exciting'), (), ('mythology', 'magic', 'family')
    ),
    'together-we-burn': _details(
        '9781250803368', 368, ('ebook', 'audiobook'), ('exciting', 'suspenseful'), (), ('dragons', 'family', 'puzzles')
    ),
    'blazewrath-games': _details(
        '9781645670797', None, ('print',), ('exciting', 'suspenseful'), (), ('dragons', 'sports', 'identity')
    ),
    'the-floating-world': _details(
        '9781250853080', 368, ('print',), ('exciting', 'suspenseful'), (), ('magic', 'family', 'identity')
    ),
    'the-wild-robot-escapes': _details(
        '9780316382045', 288, ('print', 'ebook', 'audiobook'), ('exciting', 'thoughtful'), ('illustrated', 'short_chapters'), ('nature', 'animals', 'family'),
        series=('wild-robot', 'The Wild Robot', 2)
    ),
    'the-wild-robot-protects': _details(
        '9780316669412', 288, ('print', 'ebook', 'audiobook'), ('exciting', 'thoughtful'), ('illustrated', 'short_chapters'), ('nature', 'animals', 'family'),
        series=('wild-robot', 'The Wild Robot', 3)
    ),
    'the-sea-of-monsters': _details(
        '9781368051491', 320, ('print', 'ebook', 'audiobook'), ('exciting', 'funny'), (), ('mythology', 'friendship', 'magic'),
        series=('percy-jackson', 'Percy Jackson and the Olympians', 2)
    ),
    'the-titans-curse': _details(
        '9781368051484', 352, ('print', 'ebook', 'audiobook'), ('exciting', 'suspenseful'), (), ('mythology', 'friendship', 'magic'),
        series=('percy-jackson', 'Percy Jackson and the Olympians', 3)
    ),
    'the-knight-at-dawn': _details(
        '9780679824121', 80, ('print', 'ebook', 'audiobook'), ('exciting', 'suspenseful'), ('illustrated', 'short_chapters'), ('history', 'magic', 'puzzles', 'family'),
        series=('magic-tree-house', 'Magic Tree House', 2)
    ),
    'mummies-in-the-morning': _details(
        '9780679824244', 80, ('print', 'ebook', 'audiobook'), ('exciting', 'suspenseful'), ('illustrated', 'short_chapters'), ('history', 'magic', 'puzzles', 'family'),
        series=('magic-tree-house', 'Magic Tree House', 3)
    ),
    'eldest': _details(
        '9780375840401', 720, ('print', 'ebook', 'audiobook'), ('exciting', 'suspenseful'), (), ('dragons', 'magic', 'family'),
        series=('inheritance-cycle', 'The Inheritance Cycle', 2)
    ),
    'brisingr': _details(
        '9780375826740', 816, ('print', 'ebook', 'audiobook'), ('exciting', 'suspenseful'), (), ('dragons', 'magic', 'family'),
        series=('inheritance-cycle', 'The Inheritance Cycle', 3)
    ),
    'the-boy-who-harnessed-the-wind': _details(
        '9780147510426', 304, ('print', 'ebook', 'audiobook'), ('thoughtful', 'exciting'), ('illustrated',), ('inventors', 'nature', 'family')
    ),
    'who-was-marie-curie': _details(
        '9780448478968', 112, ('print', 'ebook', 'audiobook'), ('thoughtful',), ('illustrated', 'short_chapters'), ('inventors', 'history')
    ),
    'who-was-albert-einstein': _details(
        '9780448424965', 112, ('print', 'ebook', 'audiobook'), ('thoughtful',), ('illustrated', 'short_chapters'), ('inventors', 'space', 'history')
    ),
    'what-is-nasa': _details(
        '9781524786038', 112, ('print', 'ebook'), ('exciting', 'thoughtful'), ('illustrated', 'short_chapters'), ('space', 'inventors', 'history')
    ),
    'where-is-our-solar-system': _details(
        '9780515158182', 112, ('print', 'ebook', 'audiobook'), ('thoughtful', 'exciting'), ('illustrated', 'short_chapters'), ('space', 'history')
    ),
    'the-mona-lisa-vanishes': _details(
        '9780593904213', 288, ('print', 'ebook', 'audiobook'), ('suspenseful', 'funny'), ('illustrated',), ('history', 'puzzles')
    ),
    'how-we-got-to-the-moon': _details(
        '9780525647416', 264, ('print', 'ebook'), ('exciting', 'thoughtful'), ('illustrated',), ('space', 'inventors', 'history')
    ),
    'the-watcher': _details(
        '9780375867743', 48, ('print', 'ebook'), ('cozy', 'thoughtful'), ('illustrated',), ('animals', 'nature', 'history')
    ),
    'roller-girl': _details(
        '9780525429678', 256, ('print', 'ebook', 'audiobook'), ('exciting', 'thoughtful'), ('graphic_novel',), ('sports', 'friendship', 'identity')
    ),
    'when-stars-are-scattered': _details(
        '9780525553915', 264, ('print', 'ebook', 'audiobook'), ('thoughtful',), ('graphic_novel',), ('family', 'friendship', 'identity')
    ),
    'super-narwhal-and-jelly-jolt': _details(
        '9781101919194', 64, ('print', 'ebook', 'audiobook'), ('funny', 'cozy'), ('graphic_novel', 'short_chapters'), ('animals', 'friendship'),
        series=('narwhal-and-jelly', 'Narwhal and Jelly', 2)
    ),
    'before-the-ever-after': _details(
        '9780399545443', 176, ('print', 'ebook', 'audiobook'), ('thoughtful',), ('verse',), ('family', 'sports', 'music')
    ),
    'locomotion': _details(
        '9780142415528', 144, ('print', 'ebook'), ('thoughtful',), ('verse',), ('family', 'identity', 'friendship')
    ),
    'starfish': _details(
        '9781984814524', 256, ('print', 'ebook', 'audiobook'), ('thoughtful',), ('verse',), ('identity', 'friendship', 'family')
    ),
    'the-dream-keeper-and-other-poems': _details(
        '9780679883470', 96, ('print', 'ebook'), ('cozy', 'thoughtful'), ('verse', 'illustrated'), ('identity', 'music', 'history')
    ),
    'escape-from-mr-lemoncellos-library': _details(
        '9780307931474', 336, ('print', 'ebook', 'audiobook'), ('funny', 'suspenseful'), (), ('puzzles', 'friendship')
    ),
    'the-london-eye-mystery': _details(
        '9780385751841', 336, ('print', 'ebook'), ('suspenseful', 'thoughtful'), (), ('puzzles', 'family')
    ),
    'the-absent-author': _details(
        '9780679881681', 96, ('print', 'ebook', 'audiobook'), ('suspenseful', 'exciting'), ('illustrated', 'short_chapters'), ('puzzles', 'friendship')
    ),
    'cam-jansen-the-mystery-of-the-stolen-diamonds': _details(
        '9780142400104', 64, ('print', 'ebook', 'audiobook'), ('suspenseful', 'exciting'), ('illustrated', 'short_chapters'), ('puzzles', 'friendship')
    ),
    'harbor-me': _details(
        '9780525515142', 192, ('print', 'ebook', 'audiobook'), ('thoughtful',), (), ('family', 'friendship', 'identity')
    ),
    'the-first-rule-of-punk': _details(
        '9780425290422', 336, ('print', 'ebook', 'audiobook'), ('funny', 'exciting'), ('illustrated',), ('music', 'identity', 'friendship')
    ),
    'clean-getaway': _details(
        '9781984893000', 240, ('print', 'ebook', 'audiobook'), ('thoughtful', 'exciting'), ('illustrated',), ('family', 'history')
    ),
    'the-stars-beneath-our-feet': _details(
        '9781524701277', 304, ('print', 'ebook', 'audiobook'), ('thoughtful',), (), ('family', 'friendship', 'identity')
    ),
    'the-sun-is-also-a-star': _details(
        '9780553496680', 384, ('print', 'ebook', 'audiobook'), ('thoughtful',), (), ('family', 'identity')
    ),
    'everything-everything': _details(
        '9780553496642', 336, ('print', 'ebook', 'audiobook'), ('thoughtful', 'suspenseful'), ('illustrated', 'short_chapters'), ('family', 'identity')
    ),
    'real-friends': _details(
        '9781626727854', 224, ('print',), ('thoughtful', 'funny'), ('graphic_novel',), ('friendship', 'identity')
    ),
    'stargazing': _details(
        '9781250183873', 224, ('print',), ('thoughtful',), ('graphic_novel',), ('friendship', 'family', 'identity')
    ),
    'american-born-chinese': _details(
        '9781250811899', 240, ('print',), ('thoughtful', 'funny'), ('graphic_novel',), ('identity', 'mythology', 'friendship')
    ),
}


ADDITIONAL_BOOKS = (
    {
        'id': 'the-wild-robot-escapes',
        'title': 'The Wild Robot Escapes',
        'author': 'Peter Brown',
        'interests': ('animals', 'science', 'friendship', 'adventure'),
        'age_min': 8,
        'age_max': 12,
        'description': 'Roz must learn the routines of a farm while planning a journey back to the island and the animal family she misses.',
        'source_url': 'https://www.hachettebookgroup.com/titles/peter-brown/the-wild-robot-escapes/9780316382045/',
    },
    {
        'id': 'the-wild-robot-protects',
        'title': 'The Wild Robot Protects',
        'author': 'Peter Brown',
        'interests': ('animals', 'science', 'adventure'),
        'age_min': 8,
        'age_max': 12,
        'description': 'When polluted waters threaten her island, Roz travels across the ocean to discover what is happening and help protect her home.',
        'source_url': 'https://www.hachettebookgroup.com/titles/peter-brown/the-wild-robot-protects/9780316669412/',
    },
    {
        'id': 'the-sea-of-monsters',
        'title': 'The Sea of Monsters',
        'author': 'Rick Riordan',
        'interests': ('fantasy', 'adventure', 'humor'),
        'age_min': 8,
        'age_max': 14,
        'description': 'Percy and his friends sail into dangerous waters to rescue Grover and find a way to restore the safety of Camp Half-Blood.',
        'source_url': 'https://books.disney.com/book/the-sea-of-monsters/',
    },
    {
        'id': 'the-titans-curse',
        'title': 'The Titan’s Curse',
        'author': 'Rick Riordan',
        'interests': ('fantasy', 'adventure', 'mystery'),
        'age_min': 8,
        'age_max': 14,
        'description': 'A missing goddess and a mysterious monster send Percy and his friends on a winter quest with Olympus at stake.',
        'source_url': 'https://books.disney.com/book/the-titans-curse/',
    },
    {
        'id': 'the-knight-at-dawn',
        'title': 'The Knight at Dawn',
        'author': 'Mary Pope Osborne',
        'interests': ('adventure', 'fantasy', 'history'),
        'age_min': 6,
        'age_max': 9,
        'description': 'Jack and Annie explore a medieval castle, where a feast, a secret passage and an unexpected knight turn their visit into an adventure.',
        'source_url': 'https://www.penguinrandomhouse.com/books/125127/the-knight-at-dawn-by-mary-pope-osborne-illustrated-by-sal-murdocca/',
    },
    {
        'id': 'mummies-in-the-morning',
        'title': 'Mummies in the Morning',
        'author': 'Mary Pope Osborne',
        'interests': ('adventure', 'fantasy', 'history'),
        'age_min': 6,
        'age_max': 9,
        'description': 'Inside an Egyptian pyramid, Jack and Annie help a long-dead queen solve a riddle while searching for a way back to their tree house.',
        'source_url': 'https://www.penguinrandomhouse.com/books/125139/mummies-in-the-morning-by-mary-pope-osborne-ilustrated-by-sal-murdocca/',
    },
    {
        'id': 'eldest',
        'title': 'Eldest',
        'author': 'Christopher Paolini',
        'interests': ('fantasy', 'adventure', 'animals'),
        'age_min': 12,
        'age_max': None,
        'description': 'Eragon and Saphira travel to the elves to develop their abilities while new dangers grow at home. The second Inheritance Cycle adventure.',
        'source_url': 'https://www.penguinrandomhouse.com/books/126441/eldest-by-christopher-paolini/',
    },
    {
        'id': 'brisingr',
        'title': 'Brisingr',
        'author': 'Christopher Paolini',
        'interests': ('fantasy', 'adventure', 'animals'),
        'age_min': 12,
        'age_max': None,
        'description': 'Eragon and Saphira face competing promises and difficult choices as the resistance prepares for its next struggle against the empire.',
        'source_url': 'https://www.penguinrandomhouse.com/books/126439/brisingr-by-christopher-paolini/',
    },
    {
        'id': 'the-boy-who-harnessed-the-wind',
        'title': 'The Boy Who Harnessed the Wind (Young Readers Edition)',
        'author': 'William Kamkwamba and Bryan Mealer',
        'interests': ('science', 'history'),
        'age_min': 10,
        'age_max': None,
        'description': 'William Kamkwamba tells how curiosity, library books and salvaged materials helped him build a windmill in Malawi. Adapted for young readers.',
        'source_url': 'https://www.penguinrandomhouse.com/books/314792/the-boy-who-harnessed-the-wind-movie-tie-in-edition-by-william-kamkwamba-and-bryan-mealer-illustrated-by-anna-hymas/9780147510426/',
    },
    {
        'id': 'who-was-marie-curie',
        'title': 'Who Was Marie Curie?',
        'author': 'Megan Stine and Who HQ',
        'interests': ('science', 'history'),
        'age_min': 8,
        'age_max': 12,
        'description': 'Meet a scientist whose determination led to discoveries about radioactivity and two Nobel Prizes in this illustrated biography.',
        'source_url': 'https://www.penguinrandomhouse.com/books/314462/who-was-marie-curie-by-megan-stine-illustrated-by-ted-hammond/9780448478968/',
    },
    {
        'id': 'who-was-albert-einstein',
        'title': 'Who Was Albert Einstein?',
        'author': 'Jess Brallier and Who HQ',
        'interests': ('science', 'history'),
        'age_min': 8,
        'age_max': 12,
        'description': 'An illustrated biography follows Einstein from his childhood questions to ideas that changed how scientists understand the universe.',
        'source_url': 'https://www.penguinrandomhouse.com/books/290276/who-was-albert-einstein-by-jess-brallier-illustrated-by-robert-andrew-parker/',
    },
    {
        'id': 'what-is-nasa',
        'title': 'What Is NASA?',
        'author': 'Sarah Fabiny and Who HQ',
        'interests': ('science', 'history'),
        'age_min': 8,
        'age_max': 12,
        'description': 'Explore the people, missions and discoveries behind NASA, from the space race to journeys beyond Earth.',
        'source_url': 'https://www.penguinrandomhouse.com/books/559589/what-is-nasa-by-sarah-fabiny-illustrated-by-ted-hammond/',
    },
    {
        'id': 'where-is-our-solar-system',
        'title': 'Where Is Our Solar System?',
        'author': 'Stephanie Sabol and Who HQ',
        'interests': ('science', 'history'),
        'age_min': 8,
        'age_max': 12,
        'description': "Tour planets, moons and smaller worlds while discovering how astronomers changed our understanding of Earth's place in space.",
        'source_url': 'https://www.penguinrandomhouse.com/books/550095/where-is-our-solar-system-by-stephanie-sabol-illustrated-by-ted-hammond/',
    },
    {
        'id': 'the-mona-lisa-vanishes',
        'title': 'The Mona Lisa Vanishes',
        'author': 'Nicholas Day',
        'interests': ('history', 'mystery', 'humor'),
        'age_min': 10,
        'age_max': 14,
        'description': 'A real art theft becomes a lively historical puzzle as detectives search for the missing Mona Lisa and the person who took it.',
        'source_url': 'https://www.penguinrandomhouse.com/books/714730/the-mona-lisa-vanishes-by-nicholas-day-illustrated-by-brett-helquist/',
    },
    {
        'id': 'how-we-got-to-the-moon',
        'title': 'How We Got to the Moon',
        'author': 'John Rocco',
        'interests': ('science', 'history', 'adventure'),
        'age_min': 10,
        'age_max': None,
        'description': 'Illustrated diagrams and human stories reveal the engineers, builders and problem-solving behind the first Moon landing.',
        'source_url': 'https://www.penguinrandomhouse.com/books/588478/how-we-got-to-the-moon-by-john-rocco/',
    },
    {
        'id': 'the-watcher',
        'title': 'The Watcher',
        'author': 'Jeanette Winter',
        'interests': ('animals', 'science', 'history'),
        'age_min': 4,
        'age_max': 8,
        'description': 'An illustrated life of Jane Goodall follows her careful observations of chimpanzees and her work to protect their forest homes.',
        'source_url': 'https://www.penguinrandomhouse.com/books/205019/the-watcher-by-jeanette-winter-illustrated-by-jeanette-winter/',
    },
    {
        'id': 'roller-girl',
        'title': 'Roller Girl',
        'author': 'Victoria Jamieson',
        'interests': ('friendship', 'adventure'),
        'age_min': 9,
        'age_max': 12,
        'description': 'Astrid tries roller derby while her best friend chooses a different path. A graphic novel about practice, changing friendships and finding confidence.',
        'source_url': 'https://www.penguinrandomhouse.com/books/313687/roller-girl-by-victoria-jamieson/',
    },
    {
        'id': 'when-stars-are-scattered',
        'title': 'When Stars Are Scattered',
        'author': 'Victoria Jamieson and Omar Mohamed',
        'interests': ('friendship', 'history'),
        'age_min': 9,
        'age_max': 12,
        'description': 'Omar and his brother grow up in a Kenyan refugee camp, balancing school, family responsibilities and hope in this graphic memoir.',
        'source_url': 'https://www.penguinrandomhouse.com/books/599538/when-stars-are-scattered-by-victoria-jamieson-and-omar-mohamed-illustrated-by-victoria-jamieson-color-by-iman-geddy/',
    },
    {
        'id': 'super-narwhal-and-jelly-jolt',
        'title': 'Super Narwhal and Jelly Jolt (A Narwhal and Jelly Book #2)',
        'author': 'Ben Clanton',
        'interests': ('animals', 'friendship', 'humor'),
        'age_min': 6,
        'age_max': 9,
        'description': 'Narwhal and Jelly invent superhero identities, help a friend and discover that small acts of kindness can be powerful.',
        'source_url': 'https://www.penguinrandomhouse.com/books/534558/super-narwhal-and-jelly-jolt-a-narwhal-and-jelly-book-2-by-ben-clanton/',
    },
    {
        'id': 'before-the-ever-after',
        'title': 'Before the Ever After',
        'author': 'Jacqueline Woodson',
        'interests': ('friendship',),
        'age_min': 10,
        'age_max': None,
        'description': 'ZJ turns to friends, music and family memories as his football-star father struggles with lasting head injuries. A story told in verse.',
        'source_url': 'https://www.penguinrandomhouse.com/books/535796/before-the-ever-after-by-jacqueline-woodson/',
    },
    {
        'id': 'locomotion',
        'title': 'Locomotion',
        'author': 'Jacqueline Woodson',
        'interests': ('friendship',),
        'age_min': 10,
        'age_max': None,
        'description': 'Lonnie uses poetry to remember his parents, stay connected to his sister and begin to feel at home with a new family.',
        'source_url': 'https://www.penguinrandomhouse.com/books/286727/locomotion-by-jacqueline-woodson/',
    },
    {
        'id': 'starfish',
        'title': 'Starfish',
        'author': 'Lisa Fipps',
        'interests': ('friendship',),
        'age_min': 10,
        'age_max': None,
        'description': 'Ellie finds support in friendship, swimming and a trusted therapist as she learns to challenge hurtful messages about her body. Told in verse.',
        'source_url': 'https://www.penguinrandomhouse.com/books/608212/starfish-by-lisa-fipps/',
    },
    {
        'id': 'the-dream-keeper-and-other-poems',
        'title': 'The Dream Keeper and Other Poems',
        'author': 'Langston Hughes',
        'interests': ('history',),
        'age_min': 8,
        'age_max': 12,
        'description': "Langston Hughes's poems explore dreams, music and everyday life, with scratchboard illustrations by Brian Pinkney.",
        'source_url': 'https://www.penguinrandomhouse.com/books/84094/the-dream-keeper-and-other-poems-by-langston-hughes/',
    },
    {
        'id': 'escape-from-mr-lemoncellos-library',
        'title': "Escape from Mr. Lemoncello's Library",
        'author': 'Chris Grabenstein',
        'interests': ('mystery', 'adventure', 'humor'),
        'age_min': 8,
        'age_max': 12,
        'description': 'A library sleepover turns into a puzzle contest. Kyle and the other guests must work through clues to find the secret way out.',
        'source_url': 'https://www.penguinrandomhouse.com/books/216860/escape-from-mr-lemoncellos-library-by-chris-grabenstein/',
    },
    {
        'id': 'the-london-eye-mystery',
        'title': 'The London Eye Mystery',
        'author': 'Siobhan Dowd',
        'interests': ('mystery', 'friendship'),
        'age_min': 8,
        'age_max': 12,
        'description': 'When their cousin disappears during a ride on the London Eye, Ted and Kat piece together what they saw and follow the clues.',
        'source_url': 'https://www.penguinrandomhouse.com/books/42460/the-london-eye-mystery-by-siobhan-dowd/',
    },
    {
        'id': 'the-absent-author',
        'title': 'A to Z Mysteries: The Absent Author',
        'author': 'Ron Roy',
        'interests': ('mystery', 'friendship'),
        'age_min': 6,
        'age_max': 9,
        'description': 'A famous author fails to arrive at a bookstore signing. Dink, Josh and Ruth Rose investigate in the first A to Z mystery.',
        'source_url': 'https://www.penguinrandomhouse.com/books/158486/a-to-z-mysteries-the-absent-author-by-ron-roy-illustrated-by-john-steven-gurney/',
    },
    {
        'id': 'cam-jansen-the-mystery-of-the-stolen-diamonds',
        'title': 'Cam Jansen: the Mystery of the Stolen Diamonds #1',
        'author': 'David A. Adler',
        'interests': ('mystery', 'friendship'),
        'age_min': 7,
        'age_max': 10,
        'description': 'Cam uses her remarkable visual memory to investigate a jewelry-store robbery and help identify the real thief.',
        'source_url': 'https://www.penguinrandomhouse.com/books/292899/cam-jansen-the-mystery-of-the-stolen-diamonds-1-by-david-a-adler-illustrated-by-susanna-natti/',
    },
    {
        'id': 'harbor-me',
        'title': 'Harbor Me',
        'author': 'Jacqueline Woodson',
        'interests': ('friendship',),
        'age_min': 10,
        'age_max': None,
        'description': 'Six classmates create a space to share worries about family, belonging and the world around them, and learn to listen to one another.',
        'source_url': 'https://www.penguinrandomhouse.com/books/304852/harbor-me-by-jacqueline-woodson/',
    },
    {
        'id': 'the-first-rule-of-punk',
        'title': 'The First Rule of Punk',
        'author': 'Celia C. Pérez',
        'interests': ('friendship', 'humor'),
        'age_min': 9,
        'age_max': 12,
        'description': 'After a move to Chicago, Malú makes zines and starts a band while figuring out how to be herself at a new school.',
        'source_url': 'https://www.penguinrandomhouse.com/books/553179/the-first-rule-of-punk-by-celia-c-perez/9780425290422/',
    },
    {
        'id': 'clean-getaway',
        'title': 'Clean Getaway',
        'author': 'Nic Stone',
        'interests': ('history', 'adventure', 'friendship'),
        'age_min': 8,
        'age_max': 12,
        'description': 'Scoob joins his grandmother on an unexpected road trip through the American South, uncovering family stories and history along the way.',
        'source_url': 'https://www.penguinrandomhouse.com/books/605269/clean-getaway-by-nic-stone/9781984893000/',
    },
    {
        'id': 'the-stars-beneath-our-feet',
        'title': 'The Stars Beneath Our Feet',
        'author': 'David Barclay Moore',
        'interests': ('friendship',),
        'age_min': 10,
        'age_max': None,
        'description': 'Lolly builds an imaginative city from LEGO bricks as he works through grief and discovers new connections in his Harlem neighborhood.',
        'source_url': 'https://www.penguinrandomhouse.com/books/546296/the-stars-beneath-our-feet-by-david-barclay-moore/',
    },
    {
        'id': 'the-sun-is-also-a-star',
        'title': 'The Sun Is Also a Star',
        'author': 'Nicola Yoon',
        'interests': ('friendship',),
        'age_min': 12,
        'age_max': None,
        'description': "Natasha and Daniel meet in New York on a day when their families' expectations and Natasha's impending deportation complicate a growing connection.",
        'source_url': 'https://www.penguinrandomhouse.com/books/240387/the-sun-is-also-a-star-movie-tie-in-edition-by-nicola-yoon/9780553496680/',
    },
    {
        'id': 'everything-everything',
        'title': 'Everything, Everything',
        'author': 'Nicola Yoon',
        'interests': ('friendship', 'adventure'),
        'age_min': 12,
        'age_max': None,
        'description': 'Maddy has spent her life indoors because of a serious illness. Meeting the boy next door leads her to question what she knows about her world.',
        'source_url': 'https://www.penguinrandomhouse.com/books/240386/everything-everything-by-nicola-yoon/9780553496642/',
    },
    {
        'id': 'real-friends',
        'title': 'Real Friends',
        'author': 'Shannon Hale',
        'age_min': 8,
        'age_max': 12,
        'interests': ('friendship', 'humor'),
        'description': 'A graphic memoir follows Shannon through shifting school friendships, exclusion and the search for people who let her be herself.',
        'source_url': 'https://us.macmillan.com/books/9781626727854/realfriends/',
    },
    {
        'id': 'stargazing',
        'title': 'Stargazing',
        'author': 'Jen Wang',
        'age_min': 8,
        'age_max': 12,
        'interests': ('friendship',),
        'description': 'Christine and her new neighbor Moon form an unexpected friendship, then face a challenge that asks them to understand each other more deeply.',
        'source_url': 'https://us.macmillan.com/books/9781250183873/stargazing/',
    },
    {
        'id': 'american-born-chinese',
        'title': 'American Born Chinese',
        'author': 'Gene Luen Yang',
        'age_min': 12,
        'age_max': 18,
        'interests': ('friendship', 'fantasy', 'humor'),
        'description': 'Three interwoven graphic stories connect a new student, the Monkey King and questions about stereotypes, belonging and self-acceptance.',
        'source_url': 'https://us.macmillan.com/books/9781250811899/americanbornchinese/',
    },
)
