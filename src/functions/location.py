import requests
import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class LocationError(Exception):
    """Custom exception for location-related errors"""
    pass

class Coordinates(BaseModel):
    latitude: float
    longitude: float

    def __str__(self) -> str:
        return f"{self.latitude},{self.longitude}"

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
    location: dict[str, float]

class LocationInfo(BaseModel):
    formatted_address: str
    place_id: str
    location_type: str
    address_components: dict[str, str]

class LocationTools:
    """A simplified toolkit for location-based operations"""

    def __init__(self, api_key: str | None = None):
        """Initialize with Google Maps API key"""
        self.api_key = api_key or os.getenv('GOOGLE_MAPS_API_KEY')
        if not self.api_key:
            raise ValueError("Google Maps API key is required. Set GOOGLE_MAPS_API_KEY environment variable or pass it directly.")

        self.base_url = "https://maps.googleapis.com/maps/api"

    def _make_request(self, endpoint: str, params: dict) -> dict:
        """Make a request to Google Maps API"""
        params['key'] = self.api_key
        url = f"{self.base_url}/{endpoint}/json"

        response = requests.get(url, params=params)
        data = response.json()

        if data['status'] != 'OK':
            raise LocationError(f"API request failed: {data.get('error_message', data['status'])}")

        return data

    def get_location_info(self, coords: Coordinates) -> LocationInfo:
        """
        Get detailed location information from coordinates

        Args:
            coords: Coordinates object with latitude and longitude

        Returns:
            LocationInfo object containing address components and place information
        """
        data = self._make_request('geocode', {
            'latlng': str(coords)
        })

        result = data['results'][0]
        return LocationInfo(
            formatted_address=result['formatted_address'],
            place_id=result['place_id'],
            location_type=result['geometry']['location_type'],
            address_components={
                comp['types'][0]: comp['long_name']
                for comp in result['address_components']
            }
        )

    def search_nearby_places(self, 
                           coords: Coordinates, 
                           keyword: str | None = None,
                           radius: int = 1000,
                           place_type: str | None = None) -> list[NearbyPlace]:
        """
        Search for places near the given coordinates
        
        Args:
            coords: Coordinates object with latitude and longitude
            keyword: Optional search term
            radius: Search radius in meters (default 1000, max 50000)
            place_type: Optional type of place to search for (e.g., 'restaurant', 'park')
            
        Returns:
            List of nearby places with basic information
        """
        params = {
            'location': str(coords),
            'radius': min(radius, 50000)
        }
        
        if keyword:
            params['keyword'] = keyword
        if place_type:
            params['type'] = place_type

        data = self._make_request('place/nearbysearch', params)
        
        return [NearbyPlace(
            name=place['name'],
            place_id=place['place_id'],
            types=place['types'],
            rating=place.get('rating'),
            vicinity=place['vicinity'],
            location=place['geometry']['location']
        ) for place in data['results']]

    def get_place_details(self, place_id: str) -> PlaceDetails:
        """
        Get detailed information about a specific place
        
        Args:
            place_id: The Google Places ID for the location
            
        Returns:
            Detailed information about the place
        """
        data = self._make_request('place/details', {
            'place_id': place_id,
            'fields': 'name,formatted_address,type,rating,website,formatted_phone_number'
        })
        
        result = data['result']
        return PlaceDetails(
            name=result['name'],
            formatted_address=result['formatted_address'],
            types=result.get('types', []),
            rating=result.get('rating'),
            website=result.get('website'),
            phone_number=result.get('formatted_phone_number')
        )

# Example usage
if __name__ == "__main__":
    # Initialize tools
    tools = LocationTools()

    # Example coordinates (San Francisco Ferry Building)
    sf_coords = Coordinates(37.7955, -122.3937)

    # Get location information
    location_info = tools.get_location_info(sf_coords)
    print("\nLocation Info:")
    print(location_info)

    # Search for nearby restaurants
    nearby_places = tools.search_nearby_places(
        sf_coords,
        keyword="restaurant",
        radius=500
    )
    print("\nNearby Restaurants:")
    for place in nearby_places[:3]:  # Show first 3 results
        print(f"- {place['name']} ({place['rating']} ⭐)")

    # Get details for the first place
    if nearby_places:
        details = tools.get_place_details(nearby_places[0]['place_id'])
        print("\nFirst Restaurant Details:")
        print(details)