"""
Address Validation Module
Validates Australian addresses using Google Maps API
"""

import logging
import requests
from typing import Optional, Dict
import re
from math import radians, cos, sin, asin, sqrt

logger = logging.getLogger(__name__)


class AddressValidator:
    """
    Validates and standardizes Australian addresses using Google Maps Geocoding API
    """

    def __init__(self, google_api_key: str, timeout: int = 5):
        """
        Initialize address validator

        Args:
            google_api_key: Google Maps API key
            timeout: Request timeout in seconds
        """
        self.google_api_key = google_api_key
        self.timeout = timeout
        self.geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"

    def validate_address(
        self,
        street: str,
        suburb: str,
        postcode: str,
        state: str = 'NSW'
    ) -> Dict:
        """
        Validate an address using Google Maps

        Args:
            street: Street address (e.g., "42 Smith Street")
            suburb: Suburb/suburb name
            postcode: Australian postcode
            state: Australian state (NSW, VIC, QLD, etc.)

        Returns:
            {
                'valid': True/False/None,
                'formatted_address': str (if valid),
                'coordinates': {'lat': float, 'lng': float} (if valid),
                'suggestion': str (if invalid but suggestion available),
                'message': str (user-friendly message),
                'components': {
                    'street': str,
                    'suburb': str,
                    'postcode': str,
                    'state': str
                }
            }
        """
        try:
            # Clean inputs
            street = street.strip() if street else ""
            suburb = suburb.strip() if suburb else ""
            postcode = postcode.strip() if postcode else ""
            state = state.strip().upper() if state else "NSW"

            # Validate inputs not empty
            if not street or not suburb:
                return {
                    'valid': False,
                    'message': 'Please provide both street address and suburb',
                    'suggestion': None
                }

            # Try with full address including postcode
            query = f"{street}, {suburb} {postcode} {state}, Australia"
            logger.info(f"Validating address: {query}")

            location = self._geocode(query)

            if location:
                return {
                    'valid': True,
                    'formatted_address': location['formatted_address'],
                    'coordinates': {
                        'lat': location['lat'],
                        'lng': location['lng']
                    },
                    'components': {
                        'street': street,
                        'suburb': suburb,
                        'postcode': postcode,
                        'state': state
                    },
                    'message': 'Address validated successfully'
                }

            # If not found, try without postcode
            logger.info(f"Full address not found, trying without postcode")
            query_fallback = f"{street}, {suburb} {state}, Australia"
            location = self._geocode(query_fallback)

            if location:
                return {
                    'valid': False,
                    'message': f'Postcode might be incorrect. Did you mean: {location["formatted_address"]}?',
                    'suggestion': location['formatted_address'],
                    'coordinates': {
                        'lat': location['lat'],
                        'lng': location['lng']
                    },
                    'components': self._parse_address_components(location['formatted_address'])
                }

            # If still not found, try suburb + postcode only
            logger.info(f"Trying suburb + postcode only")
            query_suburb = f"{suburb} {postcode} {state}, Australia"
            location = self._geocode(query_suburb)

            if location:
                return {
                    'valid': False,
                    'message': 'Street address not found. Please check spelling.',
                    'suggestion': location['formatted_address'],
                    'coordinates': {
                        'lat': location['lat'],
                        'lng': location['lng']
                    }
                }

            # Complete failure
            return {
                'valid': False,
                'message': f'Address "{street}, {suburb} {postcode}" not found. Please check spelling.',
                'suggestion': None
            }

        except requests.Timeout:
            logger.warning("Address validation timeout - will try again")
            return {
                'valid': None,
                'message': 'Address check timed out. Let me take your details anyway and we\'ll confirm shortly.',
                'suggestion': None
            }

        except requests.RequestException as e:
            logger.warning(f"Geocoder service error: {str(e)}")
            return {
                'valid': None,
                'message': 'Address service unavailable. Taking your details anyway.',
                'suggestion': None
            }

        except Exception as e:
            logger.error(f"Address validation error: {str(e)}")
            return {
                'valid': None,
                'message': 'Address check failed. Taking your details anyway.',
                'suggestion': None
            }

    def validate_suburb(self, suburb: str, state: str = 'NSW') -> Optional[Dict]:
        """
        Validate if a suburb exists in a state

        Args:
            suburb: Suburb name
            state: Australian state

        Returns:
            Suburb data or None if not found
        """
        try:
            query = f"{suburb} {state}, Australia"
            location = self._geocode(query)

            if location:
                return {
                    'suburb': suburb,
                    'state': state,
                    'coordinates': {
                        'lat': location['lat'],
                        'lng': location['lng']
                    }
                }
            return None

        except Exception as e:
            logger.error(f"Suburb validation error: {str(e)}")
            return None

    def validate_postcode(self, postcode: str, state: str = 'NSW') -> Optional[Dict]:
        """
        Validate if a postcode is valid for a state

        Args:
            postcode: Australian postcode
            state: Australian state

        Returns:
            Postcode data or None if invalid
        """
        try:
            # Basic validation - Australian postcodes are 4 digits
            if not re.match(r'^\d{4}$', postcode):
                return None

            # Check range by state (basic)
            postcode_int = int(postcode)
            valid_ranges = {
                'NSW': (1000, 2999),
                'VIC': (3000, 3999),
                'QLD': (4000, 4999),
                'WA': (6000, 6999),
                'SA': (5000, 5999),
                'TAS': (7000, 7999),
                'ACT': (2600, 2621),
                'NT': (800, 900)
            }

            state = state.upper()
            if state in valid_ranges:
                start, end = valid_ranges[state]
                if start <= postcode_int <= end:
                    return {'postcode': postcode, 'state': state, 'valid': True}

            return None

        except Exception as e:
            logger.error(f"Postcode validation error: {str(e)}")
            return None

    def get_coordinates(self, suburb: str, state: str = 'NSW') -> Optional[Dict]:
        """
        Get latitude/longitude for a suburb

        Args:
            suburb: Suburb name
            state: Australian state

        Returns:
            {'lat': float, 'lng': float} or None
        """
        try:
            location = self._geocode(f"{suburb} {state}, Australia")
            if location:
                return {
                    'lat': location['lat'],
                    'lng': location['lng']
                }
            return None
        except Exception as e:
            logger.error(f"Coordinate lookup error: {str(e)}")
            return None

    def calculate_distance(
        self,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float
    ) -> float:
        """
        Calculate distance between two coordinates in km (Haversine formula)

        Args:
            lat1, lng1: First point coordinates
            lat2, lng2: Second point coordinates

        Returns:
            Distance in kilometers
        """
        lon1, lat1, lon2, lat2 = map(radians, [lng1, lat1, lng2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        km = 6371 * c
        return km

    def _parse_address_components(self, formatted_address: str) -> Dict:
        """
        Parse formatted address into components

        Args:
            formatted_address: Full formatted address string

        Returns:
            Address components
        """
        parts = formatted_address.split(',')
        return {
            'full': formatted_address,
            'parts': [p.strip() for p in parts],
            'parts_count': len(parts)
        }

    def suggest_address(self, partial_address: str) -> Optional[str]:
        """
        Suggest a full address from partial input

        Args:
            partial_address: Partial address string

        Returns:
            Full suggested address or None
        """
        try:
            location = self._geocode(partial_address + ", Australia")
            if location:
                return location['formatted_address']
            return None
        except Exception as e:
            logger.error(f"Address suggestion error: {str(e)}")
            return None

    def _geocode(self, query: str) -> Optional[Dict]:
        """
        Query Google Maps Geocoding API

        Args:
            query: Address query string

        Returns:
            {'formatted_address': str, 'lat': float, 'lng': float} or None
        """
        try:
            if not self.google_api_key or self.google_api_key == 'test':
                # Fallback for testing without API key
                logger.warning(f"No Google API key provided, returning mock result for: {query}")
                return {
                    'formatted_address': query,
                    'lat': -33.8688,  # Sydney fallback
                    'lng': 151.2093
                }

            params = {
                'address': query,
                'key': self.google_api_key,
                'region': 'au'  # Bias results to Australia
            }

            response = requests.get(
                self.geocode_url,
                params=params,
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()

                if data.get('results') and len(data['results']) > 0:
                    result = data['results'][0]
                    return {
                        'formatted_address': result.get('formatted_address'),
                        'lat': result['geometry']['location']['lat'],
                        'lng': result['geometry']['location']['lng']
                    }

            return None

        except requests.Timeout:
            logger.warning(f"Geocoding timeout for query: {query}")
            return None
        except requests.RequestException as e:
            logger.error(f"Geocoding request error: {str(e)}")
            return None
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing geocoding response: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in geocoding: {str(e)}")
            return None
