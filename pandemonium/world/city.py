# city.py — Service handler registry for city facilities.
#
# The terminal-mode visit_city() loop has been retired.
# The GUI CityScreen handles all city UI via gui/screens/city_screen.py.
# This file now serves only as the SERVICE_HANDLERS registry.

# Import all facility handlers
from pandemonium.facilities.shop import city_shop
from pandemonium.facilities.inn import inn_menu
from pandemonium.facilities.blacksmith import blacksmith_menu
from pandemonium.facilities.temple import temple_menu
from pandemonium.facilities.port import port_service
from pandemonium.facilities.shipyard import shipyard_service
from pandemonium.facilities.trade_hall import trade_hall_service
from pandemonium.facilities.barracks import barracks_service
from pandemonium.facilities.herbalist import herbalist_service
from pandemonium.facilities.arcane_tower import arcane_tower_service
from pandemonium.facilities.black_market import black_market_service
from pandemonium.facilities.guild import guild_service
from pandemonium.facilities.gift_shop import gift_shop_service
from pandemonium.facilities.star_tower import star_tower_service

# Map service names to handler functions
SERVICE_HANDLERS = {
    "shop":          city_shop,
    "inn":           inn_menu,
    "blacksmith":    blacksmith_menu,
    "port":          port_service,
    "shipyard":      shipyard_service,
    "trade_hall":    trade_hall_service,
    "temple":        temple_menu,
    "barracks":      barracks_service,
    "herbalist":     herbalist_service,
    "arcane_tower":  arcane_tower_service,
    "black_market":  black_market_service,
    "guild":         guild_service,
    "gift_shop":     gift_shop_service,
    "star_tower":    star_tower_service,
}