# Example spec used for the screenshots/benchmarks (Python literal; json.dumps() it for the tool)
SPEC = {
 "title": "San Francisco in one day",
 "sources": [{"title": "Fleet Week San Francisco 2026 schedule", "url": "https://fleetweeksf.org/schedule/"}, {"title": "Golden Gate Bridge – visitor info", "url": "https://www.goldengate.org/"}],
 "blocks": [
  {"type": "text", "md": "I'd plan a **9 AM–7 PM route** that starts downtown, takes you through the city's iconic streets and waterfront, and finishes with panoramic views at sunset."},
  {"type": "images", "items": [{"query": "Golden Gate Bridge from Baker Beach", "caption": "Golden Gate Bridge"}, {"query": "Lombard Street San Francisco crooked street", "caption": "Lombard Street"}, {"query": "Palace of Fine Arts San Francisco", "caption": "Palace of Fine Arts"}]},
  {"type": "text", "md": "There's a bonus if you're going in early October: it's **Fleet Week**, and the Blue Angels practice over the bay in the afternoon. Time your waterfront visit for the jets [1]."},
  {"type": "map", "area": "San Francisco, CA", "route": True, "places": [
    {"name": "Ferry Building", "lat": 37.7971, "lng": -122.3946, "icon": "⛴️", "group": "Morning", "time": "9:00", "note": "Coffee and the market hall"},
    {"name": "Chinatown San Francisco", "lat": 37.7956, "lng": -122.40899999999999, "icon": "🏮", "group": "Morning", "time": "10:15", "note": "Grant Ave + cable car"},
    {"name": "Lombard Street", "lat": 37.8036, "lng": -122.4199, "icon": "🌸", "group": "Morning", "time": "11:30", "note": "The crooked block"},
    {"name": "Pier 39", "lat": 37.8102, "lng": -122.411, "icon": "🦭", "group": "Afternoon", "time": "12:30", "note": "Sea lions, lunch"},
    {"name": "Palace of Fine Arts", "lat": 37.8044, "lng": -122.4496, "icon": "🏛️", "group": "Afternoon", "time": "14:30", "note": "Lagoon walk"},
    {"name": "Crissy Field", "lat": 37.8054, "lng": -122.4657, "icon": "✈️", "group": "Afternoon", "time": "15:30", "note": "Watch the Blue Angels"},
    {"name": "Golden Gate Bridge Welcome Center", "lat": 37.8088, "lng": -122.4764, "icon": "🌉", "group": "Evening", "time": "17:00", "note": "Walk out onto the span"},
    {"name": "Painted Ladies Alamo Square", "lat": 37.7777, "lng": -122.434, "icon": "🏠", "group": "Evening", "time": "18:30", "note": "Sunset over the skyline"}]},
  {"type": "timeline", "items": [
    {"time": "9:00 AM", "title": "Ferry Building", "detail": "Coffee, pastries and the bay at the foot of Market St.", "place": "Ferry Building"},
    {"time": "10:15 AM", "title": "Chinatown + cable car", "detail": "Walk Grant Ave, then ride the Powell–Hyde line.", "place": "Chinatown San Francisco"},
    {"time": "12:30 PM", "title": "Pier 39 & Fisherman's Wharf", "detail": "Sea lions and clam chowder.", "place": "Pier 39"},
    {"time": "3:30 PM", "title": "Crissy Field", "detail": "Best seat for the Blue Angels practice.", "place": "Crissy Field"},
    {"time": "6:30 PM", "title": "Painted Ladies at sunset", "detail": "Alamo Square park, skyline behind the houses.", "place": "Painted Ladies Alamo Square"}]},
  {"type": "places", "title": "Where to eat", "area": "San Francisco", "items": [
    {"name": "Tartine Bakery", "subtitle": "Mission", "rating": 4.6, "price": "$$", "tags": ["Bakery"], "description": "Morning buns and country loaves worth the line.", "image": "Tartine Bakery San Francisco"},
    {"name": "Swan Oyster Depot", "subtitle": "Nob Hill", "rating": 4.7, "price": "$$$", "tags": ["Seafood"], "description": "Counter-only seafood institution since 1912.", "image": "Swan Oyster Depot"},
    {"name": "House of Prime Rib", "subtitle": "Van Ness", "rating": 4.6, "price": "$$$", "tags": ["Classic"], "description": "Tableside carved prime rib in a clubby room.", "image": "House of Prime Rib San Francisco"}]},
  {"type": "callout", "tone": "tip", "title": "Getting around", "md": "Buy a **Clipper card** or use Apple/Google Pay on Muni and cable cars; the route above is about a day of walking plus two short rides."}
 ],
 "followups": ["Make it a two-day itinerary", "Swap in kid-friendly stops", "Where should I stay nearby?"]
}