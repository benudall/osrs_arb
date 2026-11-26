"""Add missing cooking recipes curated from the OSRS wiki Cooking/Experience
table (https://oldschool.runescape.wiki/w/Cooking/Experience_table).

Candidates are hand-picked to fit the arbitrage model: one craft per recipe.
GE prices are NOT required: items without price history are resolved to ids
via their OSRS wiki infoboxes (itemdata.fetch_wiki_meta) and baked with
static metadata only — the FE shows those rows with partial craft costs
(marked *) and alchemy payouts. Only items with no resolvable item id are
skipped. Excluded by design: burnt/ruined/servery items, quest/event items,
POH barrels/kegs, mature ale variants.

Usage (from backend/):  python scripts/add_cooking.py [--dry-run]
"""
import json
import sys

sys.path.insert(0, ".")
import config  # noqa: E402
import itemdata  # noqa: E402
import recipes as recipes_mod  # noqa: E402
import urllib.request  # noqa: E402

# (id, product, level, xp, materials, note)  — xp from the wiki XP table.
C = [
    # --- fish / game meat (raw -> cooked) ---
    ("karambwanji", "Karambwanji", 1, 10.0, [("Raw karambwanji", 1)], None),
    ("cooked_karambwan", "Cooked karambwan", 30, 190.0, [("Raw karambwan", 1)], "2-tick cook with Karambwan vessel."),
    ("cooked_slimy_eel", "Cooked slimy eel", 28, 95.0, [("Raw slimy eel", 1)], None),
    ("cooked_bream", "Cooked bream", 30, 45.0, [("Raw bream", 1)], None),
    ("cooked_barb_tailed_kebbit", "Cooked barb-tailed kebbit", 32, 106.0, [("Raw barb-tailed kebbit", 1)], None),
    ("cooked_wild_kebbit", "Cooked wild kebbit", 23, 73.0, [("Raw wild kebbit", 1)], None),
    ("cooked_larupia", "Cooked larupia", 31, 92.0, [("Raw larupia", 1)], None),
    ("cooked_graahk", "Cooked graahk", 41, 124.0, [("Raw graahk", 1)], None),
    ("cooked_kyatt", "Cooked kyatt", 51, 143.0, [("Raw kyatt", 1)], None),
    ("cooked_jubbly", "Cooked jubbly", 41, 160.0, [("Raw jubbly", 1)], None),
    ("cooked_pyre_fox", "Cooked pyre fox", 59, 154.0, [("Raw pyre fox", 1)], None),
    ("cooked_sunlight_antelope", "Cooked sunlight antelope", 68, 175.0, [("Raw sunlight antelope", 1)], None),
    ("cooked_moonlight_antelope", "Cooked moonlight antelope", 92, 220.0, [("Raw moonlight antelope", 1)], None),
    ("cooked_dashing_kebbit", "Cooked dashing kebbit", 82, 215.0, [("Raw dashing kebbit", 1)], None),
    ("cooked_t_bone_steak", "Cooked t-bone steak", 13, 90.0, [("Raw t-bone steak", 1)], None),
    ("cooked_chompy", "Cooked chompy", 30, 140.0, [("Raw chompy", 1)], None),
    ("cooked_giant_crab_meat", "Cooked giant crab meat", 21, 100.0, [("Giant crab meat", 1)], None),
    ("thin_snail_meat", "Thin snail meat", 12, 70.0, [("Thin snail", 1)], None),
    ("lean_snail_meat", "Lean snail meat", 17, 80.0, [("Lean snail", 1)], None),
    ("fat_snail_meat", "Fat snail meat", 22, 95.0, [("Fat snail", 1)], None),
    ("lava_eel", "Lava eel", 53, 30.0, [("Raw lava eel", 1)], None),
    ("cavefish", "Cavefish", 20, 23.0, [("Raw cavefish", 1)], None),
    ("catfish", "Catfish", 46, 43.0, [("Raw catfish", 1)], None),
    ("tetra", "Tetra", 33, 31.0, [("Raw tetra", 1)], None),
    ("guppy", "Guppy", 7, 12.0, [("Raw guppy", 1)], None),
    ("roe", "Roe", 1, 10.0, [("Leaping trout", 1)], None),
    ("caviar", "Caviar", 1, 15.0, [("Leaping sturgeon", 1)], None),
    ("pysk_fish", "Pysk fish (0)", 1, 10.0, [("Raw pysk fish (0)", 1)], None),
    ("suphi_fish", "Suphi fish (1)", 15, 13.0, [("Raw suphi fish (1)", 1)], None),
    ("leckish_fish", "Leckish fish (2)", 30, 16.0, [("Raw leckish fish (2)", 1)], None),
    ("brawk_fish", "Brawk fish (3)", 45, 19.0, [("Raw brawk fish (3)", 1)], None),
    ("mycil_fish", "Mycil fish (4)", 60, 22.0, [("Raw mycil fish (4)", 1)], None),
    ("roqed_fish", "Roqed fish (5)", 75, 25.0, [("Raw roqed fish (5)", 1)], None),
    ("kyren_fish", "Kyren fish (6)", 90, 28.0, [("Raw kyren fish (6)", 1)], None),
    ("stuffed_snake", "Stuffed snake", 70, 180.0, [("Raw stuffed snake", 1)], None),
    ("cooked_oomlie_wrap", "Cooked oomlie wrap", 50, 30.0, [("Wrapped oomlie", 1)], None),
    ("wrapped_oomlie", "Wrapped oomlie", 50, 10.0, [("Raw oomlie", 1), ("Palm leaf", 1)], None),
    ("spider_on_stick", "Spider on stick", 16, 80.0, [("Spider on stick (raw)", 1)], None),
    ("spider_on_shaft", "Spider on shaft", 16, 80.0, [("Spider on shaft (raw)", 1)], None),
    ("blood_sac", "Blood sac", 1, 20.0, [("Leechfin", 1)], None),
    ("zulrahs_scales", "Zulrah's scales", 72, 118.0, [("Sacred eel", 1)], "XP varies 109-127 per snake."),
    # --- bread / dough ---
    ("bread_dough", "Bread dough", 1, 0.0, [("Pot of flour", 1), ("Bucket of water", 1)], None),
    ("bread", "Bread", 1, 40.0, [("Bread dough", 1)], None),
    ("pitta_dough", "Pitta dough", 58, 0.0, [("Pot of flour", 1), ("Bucket of water", 1)], None),
    ("pitta_bread", "Pitta bread", 58, 40.0, [("Pitta dough", 1)], None),
    ("ugthanki_kebab", "Ugthanki kebab", 1, 40.0, [("Kebab mix", 1), ("Pitta bread", 1)], None),
    # --- potatoes & toppings ---
    ("baked_potato", "Baked potato", 7, 15.0, [("Potato", 1)], None),
    ("cooked_sweetcorn", "Cooked sweetcorn", 28, 104.0, [("Sweetcorn", 1)], None),
    ("pat_of_butter", "Pat of butter", 38, 40.5, [("Bucket of milk", 1)], None),
    ("cheese", "Cheese", 48, 64.0, [("Bucket of milk", 1)], None),
    ("uncooked_egg", "Uncooked egg", 13, 0.0, [("Egg", 1), ("Bowl", 1)], None),
    ("scrambled_egg", "Scrambled egg", 13, 50.0, [("Uncooked egg", 1)], None),
    ("egg_and_tomato", "Egg and tomato", 23, 0.0, [("Scrambled egg", 1), ("Tomato", 1)], None),
    ("spicy_sauce", "Spicy sauce", 9, 25.0, [("Chopped garlic", 1), ("Gnome spice", 1)], None),
    ("chilli_con_carne", "Chilli con carne", 11, 0.0, [("Spicy sauce", 1), ("Cooked meat", 1)], None),
    ("fried_onions", "Fried onions", 42, 60.0, [("Chopped onion", 1)], None),
    ("fried_mushrooms", "Fried mushrooms", 46, 60.0, [("Sliced mushrooms", 1)], None),
    ("mushroom_and_onion", "Mushroom & onion", 57, 0.0, [("Fried mushrooms", 1), ("Fried onions", 1)], None),
    ("potato_with_butter", "Potato with butter", 39, 40.0, [("Baked potato", 1), ("Pat of butter", 1)], None),
    ("potato_with_cheese", "Potato with cheese", 47, 40.0, [("Potato with butter", 1), ("Cheese", 1)], None),
    ("chilli_potato", "Chilli potato", 41, 15.0, [("Chilli con carne", 1), ("Potato with butter", 1)], None),
    ("egg_potato", "Egg potato", 51, 45.0, [("Egg and tomato", 1), ("Potato with butter", 1)], None),
    ("mushroom_potato", "Mushroom potato", 64, 55.0, [("Mushroom & onion", 1), ("Potato with butter", 1)], None),
    ("tuna_and_corn", "Tuna and corn", 67, 0.0, [("Sweetcorn (bowl)", 1), ("Tuna", 1)], None),
    ("tuna_potato", "Tuna potato", 68, 10.0, [("Tuna and corn", 1), ("Potato with butter", 1)], None),
    # --- pies / cakes / pizzas ---
    ("uncooked_berry_pie", "Uncooked berry pie", 10, 0.0,
     [("Redberries", 1), ("Pie shell", 1)], None),
    ("uncooked_apple_pie", "Uncooked apple pie", 30, 0.0,
     [("Cooking apple", 1), ("Pie shell", 1)], None),
    ("uncooked_meat_pie", "Uncooked meat pie", 20, 0.0,
     [("Cooked meat", 1), ("Pie shell", 1)], None),
    ("uncooked_mushroom_pie", "Uncooked mushroom pie", 60, 0.0,
     [("Sulliuscep cap", 1), ("Pie shell", 1)], None),
    ("uncooked_botanical_pie", "Uncooked botanical pie", 52, 0.0,
     [("Golovanova fruit top", 1), ("Pie shell", 1)], None),
    ("uncooked_dragonfruit_pie", "Uncooked dragonfruit pie", 73, 0.0,
     [("Dragonfruit", 1), ("Pie shell", 1)], None),
    ("raw_mud_pie", "Raw mud pie", 29, 0.0,
     [("Pie shell", 1), ("Compost", 1), ("Bucket of water", 1), ("Clay", 1)],
     "Filling added in stages (compost, water, clay) - combined steps."),
    ("raw_garden_pie", "Raw garden pie", 34, 0.0,
     [("Pie shell", 1), ("Tomato", 1), ("Onion", 1), ("Cabbage", 1)],
     "Filling added in stages (tomato, onion, cabbage) - combined steps."),
    ("raw_fish_pie", "Raw fish pie", 47, 0.0,
     [("Pie shell", 1), ("Trout", 1), ("Cod", 1), ("Potato", 1)],
     "Filling added in stages (trout, cod, potato) - combined steps."),
    ("raw_admiral_pie", "Raw admiral pie", 70, 0.0,
     [("Pie shell", 1), ("Salmon", 1), ("Tuna", 1), ("Potato", 1)],
     "Filling added in stages (salmon, tuna, potato) - combined steps."),
    ("raw_wild_pie", "Raw wild pie", 85, 0.0,
     [("Pie shell", 1), ("Raw bear meat", 1), ("Raw chompy", 1), ("Raw rabbit", 1)],
     "Filling added in stages (bear meat, chompy, rabbit) - combined steps."),
    ("raw_summer_pie", "Raw summer pie", 95, 0.0,
     [("Pie shell", 1), ("Strawberry", 1), ("Watermelon", 1), ("Cooking apple", 1)],
     "Filling added in stages (strawberry, watermelon, apple) - combined steps."),
    ("redberry_pie", "Redberry pie", 10, 78.0, [("Uncooked berry pie", 1)], None),
    ("meat_pie", "Meat pie", 20, 110.0, [("Uncooked meat pie", 1)], None),
    ("apple_pie", "Apple pie", 30, 130.0, [("Uncooked apple pie", 1)], None),
    ("mushroom_pie", "Mushroom pie", 60, 200.0, [("Uncooked mushroom pie", 1)], None),
    ("dragonfruit_pie", "Dragonfruit pie", 73, 220.0, [("Uncooked dragonfruit pie", 1)], None),
    ("cake", "Cake", 40, 180.0, [("Uncooked cake", 1)], None),
    ("chocolate_cake", "Chocolate cake", 50, 30.0, [("Cake", 1), ("Chocolate bar", 1)], None),
    ("pizza_base", "Pizza base", 35, 0.0, [("Pot of flour", 1), ("Bucket of water", 1)], None),
    ("plain_pizza", "Plain pizza", 35, 143.0, [("Uncooked pizza", 1)], None),
    ("meat_pizza", "Meat pizza", 45, 26.0, [("Plain pizza", 1), ("Cooked meat", 1)], None),
    ("anchovy_pizza", "Anchovy pizza", 55, 39.0, [("Plain pizza", 1), ("Anchovies", 1)], None),
    ("pineapple_pizza", "Pineapple pizza", 65, 45.0, [("Plain pizza", 1), ("Pineapple ring", 1)], None),
    # --- dough intermediates (no GE price history; shown for craft cost + alch) ---
    ("pastry_dough", "Pastry dough", 1, 0.0, [("Pot of flour", 1), ("Bucket of water", 1)], None),
    ("uncooked_pizza", "Uncooked pizza", 35, 0.0, [("Pizza base", 1), ("Tomato", 1), ("Cheese", 1)], None),
    ("uncooked_cake", "Uncooked cake", 40, 0.0,
     [("Egg", 1), ("Pot of flour", 1), ("Bucket of milk", 1), ("Cake tin", 1)], None),
    ("uncooked_stew", "Uncooked stew", 25, 0.0, [("Cooked meat", 1), ("Potato", 1), ("Bowl of water", 1)], None),
    ("uncooked_curry", "Uncooked curry", 60, 0.0,
     [("Cooked meat", 1), ("Potato", 1), ("Bowl of water", 1), ("Curry leaf", 3)], None),
    # --- pies / cakes / pizzas (expanded: intermediates without GE prices) ---
    ("plain_pizza", "Plain pizza", 35, 143.0,
     [("Pizza base", 1), ("Tomato", 1), ("Cheese", 1)],
     "Combined steps: base + tomato + cheese -> bake (uncooked pizza has no GE price)."),
    ("cake", "Cake", 40, 180.0,
     [("Egg", 1), ("Pot of flour", 1), ("Bucket of milk", 1), ("Cake tin", 1)],
     "Combined steps: mix in cake tin -> bake (uncooked cake has no GE price; the tin is consumed per the wiki Uncooked cake recipe)."),
    ("pie_shell", "Pie shell", 1, 0.0,
     [("Pastry dough", 1), ("Pie dish", 1)],
     "Use the dough on a pie dish; the dish is consumed (returned only if the finished pie is eaten, not sold). Craft the dough from a pot of flour + bucket of water if cheaper than buying it."),
    ("botanical_pie", "Botanical pie", 52, 180.0, [("Uncooked botanical pie", 1)], None),
    ("foresters_ration", "Forester's ration", 35, 51.1, [("Cooked chicken", 1), ("Leaves", 1)], None),
    ("kebab_mix", "Kebab mix", 1, 0.0, [("Onion & tomato", 1), ("Ugthanki meat", 1)], None),
    # --- stew / curry / wine ---
    ("stew", "Stew", 25, 117.0,
     [("Cooked meat", 1), ("Potato", 1), ("Bowl of water", 1)],
     "Combined steps: meat + potato + bowl of water -> range (uncooked stew has no GE price)."),
    ("curry", "Curry", 60, 280.0,
     [("Cooked meat", 1), ("Potato", 1), ("Bowl of water", 1), ("Curry leaf", 3)],
     "Combined steps: stew + 3 curry leaves (uncooked curry has no GE price)."),
    ("wine_of_zamorak", "Wine of Zamorak", 65, 200.0, [("Zamorak's grapes", 1), ("Jug of water", 1)], None),
    # --- dairy / misc ---
    ("pot_of_cream", "Pot of cream", 21, 18.0, [("Bucket of milk", 1)], None),
    ("soda_ash", "Soda ash", 1, 0.0, [("Seaweed", 1)], None),
    # --- gnome cooking (flour + water = gnome dough; XP totals per the wiki
    # Gnome cooking page, dough/bake/combine/garnish steps combined; raw doughs
    # have no GE price so chains are expanded to tradeable materials) ---
    ("toad_crunchies", "Toad crunchies", 10, 100.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Toad's legs", 2), ("Equa leaves", 1)], None),
    ("spicy_crunchies", "Spicy crunchies", 12, 102.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Equa leaves", 2)], None),
    ("worm_crunchies", "Worm crunchies", 14, 104.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("King worm", 2), ("Equa leaves", 1)], None),
    ("chocchip_crunchies", "Chocchip crunchies", 16, 106.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Chocolate bar", 2), ("Chocolate dust", 1)], None),
    ("fruit_batta", "Fruit batta", 25, 150.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Equa leaves", 4), ("Lime chunks", 1), ("Orange chunks", 1), ("Pineapple chunks", 1)], None),
    ("toad_batta", "Toad batta", 26, 152.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Equa leaves", 1), ("Cheese", 1), ("Toad's legs", 1)], None),
    ("worm_batta", "Worm batta", 27, 154.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("King worm", 1), ("Cheese", 1), ("Equa leaves", 1)], None),
    ("vegetable_batta", "Vegetable batta", 28, 156.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Tomato", 2), ("Dwellberries", 1), ("Onion", 1), ("Cheese", 1), ("Cabbage", 1), ("Equa leaves", 1)], None),
    ("cheese_tom_batta", "Cheese+tom batta", 29, 158.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Tomato", 1), ("Cheese", 1), ("Equa leaves", 1)], None),
    ("worm_hole", "Worm hole", 30, 170.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("King worm", 4), ("Onion", 2), ("Equa leaves", 1)], None),
    ("veg_ball", "Veg ball", 35, 175.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Onion", 2), ("Potato", 2), ("Equa leaves", 1)], None),
    ("tangled_toads_legs", "Tangled toad's legs", 40, 185.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Toad's legs", 4), ("Cheese", 2), ("Dwellberries", 1), ("Equa leaves", 2)], None),
    ("chocolate_bomb", "Chocolate bomb", 42, 190.0,
     [("Pot of flour", 1), ("Bucket of water", 1), ("Chocolate bar", 4), ("Equa leaves", 1), ("Chocolate dust", 1), ("Pot of cream", 2)], None),
    ("fruit_blast", "Fruit blast", 6, 50.0,
     [("Pineapple", 1), ("Lemon", 1), ("Orange", 1), ("Lemon slices", 1), ("Cocktail glass", 1)], None),
    ("pineapple_punch", "Pineapple punch", 8, 70.0,
     [("Pineapple", 2), ("Lemon", 1), ("Orange", 1), ("Lime chunks", 1), ("Pineapple chunks", 1), ("Orange slices", 1), ("Cocktail glass", 1)], None),
    ("wizard_blizzard", "Wizard blizzard", 18, 110.0,
     [("Vodka", 2), ("Gin", 1), ("Lime", 1), ("Lemon", 1), ("Orange", 1), ("Pineapple chunks", 1), ("Lime slices", 1), ("Cocktail glass", 1)], None),
    ("short_green_guy", "Short green guy", 20, 120.0,
     [("Vodka", 1), ("Lime", 3), ("Lime slices", 1), ("Equa leaves", 1), ("Cocktail glass", 1)], None),
    ("drunk_dragon", "Drunk dragon", 32, 160.0,
     [("Vodka", 1), ("Gin", 1), ("Dwellberries", 1), ("Pineapple chunks", 1), ("Pot of cream", 1), ("Cocktail glass", 1)], None),
    ("choc_saturday", "Choc saturday", 33, 170.0,
     [("Whisky", 1), ("Chocolate bar", 1), ("Equa leaves", 1), ("Bucket of milk", 1), ("Chocolate dust", 1), ("Pot of cream", 1), ("Cocktail glass", 1)], None),
    ("blurberry_special", "Blurberry special", 37, 180.0,
     [("Vodka", 1), ("Brandy", 1), ("Gin", 1), ("Lemon", 2), ("Orange", 1), ("Lemon chunks", 1), ("Orange chunks", 1), ("Equa leaves", 1), ("Lime slices", 1), ("Cocktail glass", 1)], None),
    # --- ales (POH brewing vat, 8 glasses per brew) ---
    ("dwarven_stout", "Dwarven stout", 19, 215.0,
     [("Bucket of water", 2), ("Barley malt", 2), ("Hammerstone hops", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
    ("asgarnian_ale", "Asgarnian ale", 24, 248.0,
     [("Bucket of water", 2), ("Barley malt", 2), ("Asgarnian hops", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
    ("greenmans_ale", "Greenman's ale", 29, 281.0,
     [("Bucket of water", 2), ("Barley malt", 2), ("Harralander", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
    ("wizards_mind_bomb", "Wizard's mind bomb", 34, 314.0,
     [("Bucket of water", 2), ("Barley malt", 2), ("Yanillian hops", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
    ("dragon_bitter", "Dragon bitter", 39, 347.0,
     [("Bucket of water", 2), ("Barley malt", 2), ("Krandorian hops", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
    ("moonlight_mead", "Moonlight mead", 44, 380.0,
     [("Bucket of water", 2), ("Barley malt", 2), ("Mushroom", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
    ("chefs_delight", "Chef's delight", 54, 446.0,
     [("Bucket of water", 2), ("Barley malt", 2), ("Chocolate dust", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
    ("slayers_respite", "Slayer's respite", 59, 479.0,
     [("Bucket of water", 2), ("Barley malt", 2), ("Wildblood hops", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
    ("apple_mush", "Apple mush", 14, 0.0,
     [("Cooking apple", 4), ("Bucket", 1)],
     "Crushed in an apple press; intermediate for cider."),
    ("cider", "Cider", 14, 182.0,
     [("Apple mush", 4), ("Ale yeast", 1), ("Beer glass", 8)],
     "POH brewing vat; takes several days. 8 glasses per brew."),
]

# reusable tools (not consumed) per recipe id. Gnome spice is a tool: every
# wiki {{Recipe}} template tags it |tools = Gnome spice (sprinkled, not used up).
TOOLS = {
    "toad_crunchies": ["Crunchy tray", "Gnome spice"],
    "spicy_crunchies": ["Crunchy tray", "Gnome spice"],
    "worm_crunchies": ["Crunchy tray", "Gnome spice"],
    "chocchip_crunchies": ["Crunchy tray", "Gnome spice"],
    "fruit_batta": ["Batta tin", "Gnome spice"], "toad_batta": ["Batta tin", "Gnome spice"],
    "worm_batta": ["Batta tin", "Gnome spice"],
    "vegetable_batta": ["Batta tin"], "cheese_tom_batta": ["Batta tin"],
    "worm_hole": ["Gnomebowl mould", "Gnome spice"], "veg_ball": ["Gnomebowl mould", "Gnome spice"],
    "tangled_toads_legs": ["Gnomebowl mould", "Gnome spice"], "chocolate_bomb": ["Gnomebowl mould"],
    "fruit_blast": ["Cocktail shaker"], "pineapple_punch": ["Cocktail shaker"],
    "wizard_blizzard": ["Cocktail shaker"], "short_green_guy": ["Cocktail shaker"],
    "drunk_dragon": ["Cocktail shaker"], "choc_saturday": ["Cocktail shaker"],
    "blurberry_special": ["Cocktail shaker"],
}

# ales come out of the brewing vat 8 glasses at a time
PRODUCT_QTY = {"dwarven_stout": 8, "asgarnian_ale": 8, "greenmans_ale": 8,
               "wizards_mind_bomb": 8, "dragon_bitter": 8, "moonlight_mead": 8,
               "chefs_delight": 8, "slayers_respite": 8}

SOURCE_NOTE_ADD = ("Cooking recipes expanded from the wiki Cooking/Experience table "
                   "(scripts/add_cooking.py); items without GE price history resolved via "
                   "wiki infoboxes and shown with partial craft cost + alchemy.")


def fetch_latest_ids() -> set[int]:
    req = urllib.request.Request(
        config.WIKI_BASE + "/latest", headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))["data"]
    return {int(k) for k, v in data.items()
            if v.get("high") is not None or v.get("low") is not None}


def main() -> int:
    dry = "--dry-run" in sys.argv
    mapping = itemdata.fetch_mapping()
    name_to_id, item_map = itemdata.index_mapping(mapping)
    lower_map = {m["name"].lower(): m["id"] for m in mapping}
    latest_ids = fetch_latest_ids()

    def resolve(name):
        if name in name_to_id:
            return name_to_id[name]
        return lower_map.get(name.lower())

    # names missing from /mapping (no GE price history): resolve via infoboxes
    all_names = [prod for _, prod, _, _, _, _ in C]
    all_names += [n for _, _, _, _, mats, _ in C for n, _ in mats]
    unresolved = sorted({n for n in all_names if resolve(n) is None})
    wiki_meta = itemdata.fetch_wiki_meta(unresolved) if unresolved else {}
    members_by_id = {int(m["id"]): bool(m.get("members")) for m in mapping}
    for n in unresolved:
        meta = wiki_meta.get(n)
        if meta and meta.get("id"):
            mid = int(meta["id"])
            name_to_id[n] = mid
            members_by_id[mid] = bool(meta.get("members"))

    existing = recipes_mod.load_recipes(config.RECIPES_DIR)
    existing_products = {r["product"]["item"] for r in existing}

    new_recipes, problems, unpriced_rows = [], [], []
    for rid, prod, level, xp, mats, note in C:
        if prod in existing_products:
            problems.append(f"SKIP dup product: {prod}")
            continue
        pid = resolve(prod)
        missing = []
        unpriced = []
        if pid is None:
            missing.append(prod)
        elif pid not in latest_ids:
            unpriced.append(prod)
        mats_out = []
        for name, qty in mats:
            mid = resolve(name)
            if mid is None:
                missing.append(name)
                continue
            if mid not in latest_ids:
                unpriced.append(name)
            mats_out.append({"item": name, "qty": qty})
        if missing:
            problems.append(f"SKIP unknown: {rid} -> {missing}")
            continue
        if unpriced:
            unpriced_rows.append(f"{rid} [{', '.join(unpriced)}]")
        members = members_by_id.get(pid, False) or any(
            members_by_id.get(resolve(n), False) for n, _ in mats)
        rec = {"id": rid, "skill": "cooking", "level": level, "xp": xp,
               "members": members,
               "product": {"item": prod, "qty": PRODUCT_QTY.get(rid, 1)},
               "materials": mats_out}
        if note:
            rec["note"] = note
        if rid in TOOLS:
            rec["tools"] = TOOLS[rid]
        new_recipes.append(rec)

    print(f"{len(new_recipes)} candidates pass, {len(problems)} skipped:")
    for p in problems:
        print("  " + p)
    if unpriced_rows:
        print(f"\n{len(unpriced_rows)} recipes reference items with no GE price "
              "(partial cost, alchemy only):")
        for u in unpriced_rows:
            print("  ~ " + u)
    print("\nAdded:")
    for r in new_recipes:
        mats = ", ".join(f"{m['qty']}x {m['item']}" for m in r["materials"])
        print(f"  {r['level']:>3} {r['product']['item']:<28} {r['xp']:>6} xp  <- {mats}")

    if dry:
        print("\ndry run, not written")
        return 0

    # append to the cooking group (write_recipes keeps per-skill files grouped)
    meta = recipes_mod.load_meta(config.RECIPES_DIR)
    if SOURCE_NOTE_ADD not in meta.get("source", ""):
        meta["source"] = (meta.get("source", "")).rstrip() + " " + SOURCE_NOTE_ADD
    recipes_mod.write_recipes(config.RECIPES_DIR, existing + new_recipes, meta=meta)
    print(f"\nWrote {len(new_recipes)} recipes to {config.RECIPES_DIR}/cooking.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
