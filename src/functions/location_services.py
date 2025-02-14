import os
from dotenv import load_dotenv
from pydantic import BaseModel, model_validator
import googlemaps
from googlemaps.places import places_nearby, place
from googlemaps.geocoding import reverse_geocode
import json

load_dotenv()

API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

if not API_KEY:
    raise ValueError("Google Maps API key is required. Set GOOGLE_MAPS_API_KEY environment variable.")

class LocationError(Exception):
    """Custom exception for location-related errors"""
    pass

class Coordinates(BaseModel):
    latitude: float
    longitude: float

    @property
    def __str__(self) -> str:
        return f"{self.latitude},{self.longitude}"

    @model_validator(mode='after')
    def validate_coordinates(self) -> 'Coordinates':
        """Validate latitude and longitude ranges"""
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Latitude must be between -90 and 90, got {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Longitude must be between -180 and 180, got {self.longitude}")
        return self

class PlaceDetails(BaseModel):
    name: str
    formatted_address: str
    types: list[str]
    rating: float | None = None
    website: str | None = None
    phone_number: str | None = None

class NearbyPlace(BaseModel):
    name: str
    place_id: str
    types: list[str]
    rating: float | None = None
    vicinity: str
    location: Coordinates

class LocationInfo(BaseModel):
    formatted_address: str
    place_id: str
    location_type: str
    address_components: dict[str, str]

gmaps = googlemaps.Client(key=API_KEY)

def get_location_info(coordinates_str: str) -> LocationInfo:
    """Get detailed location information from coordinates string

    Args:
        coordinates_str: String in format "latitude,longitude"

    Returns:
        LocationInfo object with location details

    Raises:
        LocationError: If coordinates are invalid or geocoding fails
    """
    try:
        lat, lon = map(float, coordinates_str.split(','))
        coords = Coordinates(latitude=lat, longitude=lon)
        result = reverse_geocode(gmaps, (coords.latitude, coords.longitude))

        if not result:
            raise LocationError("No results found for these coordinates")

        result = result[0]
        return LocationInfo(
            formatted_address=result['formatted_address'],
            place_id=result['place_id'],
            location_type=result['geometry']['location_type'],
            address_components={
                comp['types'][0]: comp['long_name']
                for comp in result['address_components']
            }
        )
    except ValueError:
        raise LocationError(f"Invalid coordinates format. Expected 'latitude,longitude', got: {coordinates_str}")
    except Exception as e:
        raise LocationError(f"Error getting location info: {str(e)}")

def search_nearby_places(query: str) -> list[NearbyPlace]:
    """Search for places near given coordinates with optional parameters

    Args:
        query: JSON string containing:
            - coordinates: string in format "latitude,longitude"
            - keyword: (optional) search keyword
            - radius: (optional) search radius in meters (default: 1000, max: 50000)
            - place_type: (optional) type of place to search for

    Returns:
        List of NearbyPlace objects

    Raises:
        LocationError: If parameters are invalid or search fails
    """
    try:
        params = json.loads(query)

        coords_str = params.get('coordinates')
        if not coords_str:
            raise LocationError("coordinates parameter is required")

        lat, lon = map(float, coords_str.split(','))
        coords = Coordinates(latitude=lat, longitude=lon)

        radius = min(int(params.get('radius', 1000)), 50000)

        results = places_nearby(
            gmaps,
            location=(coords.latitude, coords.longitude),
            keyword=params.get('keyword'),
            radius=radius,
            type=params.get('place_type')
        )

        return [
            NearbyPlace(
                name=place['name'],
                place_id=place['place_id'],
                types=place['types'],
                rating=place.get('rating'),
                vicinity=place['vicinity'],
                location=Coordinates(
                    latitude=place['geometry']['location']['lat'],
                    longitude=place['geometry']['location']['lng']
                )
            ) for place in results['results']
        ]
    except json.JSONDecodeError:
        raise LocationError(f"Invalid JSON query: {query}")
    except Exception as e:
        raise LocationError(f"Error searching nearby places: {str(e)}")

def get_place_details(place_id: str) -> PlaceDetails:
    """Get detailed information about a specific place

    Args:
        place_id: Google Places ID string

    Returns:
        PlaceDetails object

    Raises:
        LocationError: If place_id is invalid or details cannot be retrieved
    """
    try:
        result = place(
            gmaps,
            place_id=place_id,
            fields=['name', 'formatted_address', 'type', 'rating', 'website', 'formatted_phone_number']
        )

        return PlaceDetails(
            name=result['name'],
            formatted_address=result['formatted_address'],
            types=result.get('types', []),
            rating=result.get('rating'),
            website=result.get('website'),
            phone_number=result.get('formatted_phone_number')
        )
    except Exception as e:
        raise LocationError(f"Error getting place details: {str(e)}")

if __name__ == "__main__":
    # Example usage with new string-based interfaces
    try:
        # Get location info
        location_info = get_location_info("37.7955,-122.3937")
        print("\nLocation Info:")
        print(location_info)

        # Search for nearby restaurants
        search_query = {
            "coordinates": "37.7955,-122.3937",
            "keyword": "restaurant",
            "radius": 500,
            "place_type": "restaurant"
        }
        nearby_places = search_nearby_places(json.dumps(search_query))
        print("\nNearby Restaurants:")
        for place in nearby_places[:3]:
            print(f"- {place.name} ({place.rating} ⭐)")

        # Get details for the first place
        if nearby_places:
            details = get_place_details(nearby_places[0].place_id)
            print("\nFirst Restaurant Details:")
            print(details)

    except LocationError as e:
        print(f"Error: {e}")