import React, { useState, useEffect, useCallback } from 'react';
import Select from 'react-select';
import { MapPin, Search } from 'lucide-react';
import axios from 'axios';

const BACKEND_URL =
  process.env.REACT_APP_BACKEND_URL ||
  (window.location.hostname === 'localhost'
    ? 'http://localhost:8001'
    : 'https://dualsport-maps-backend.onrender.com');
const API = `${BACKEND_URL}/api`;

const PlaceSearch = ({ value, onChange, placeholder = "Search for a place...", className = "" }) => {
  const [options, setOptions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [inputValue, setInputValue] = useState('');

  const searchPlaces = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setOptions([]);
      return;
    }

    setIsLoading(true);
    try {
      console.log('Searching for:', query, 'API URL:', `${API}/places/search`);
      console.log('BACKEND_URL:', BACKEND_URL);
      
      const response = await axios.post(`${API}/places/search`, {
        query: query,
        limit: 10
      });

      console.log('Search response:', response.data);

      const places = response.data.map(place => ({
        value: place.value,
        label: place.label,
        coordinates: place.coordinates,
        region: place.region,
        country: place.country
      }));

      setOptions(places);
    } catch (error) {
      console.error('Place search failed:', error);
      console.error('Full error details:', error.response?.data || error.message);
      console.error('Request URL:', `${API}/places/search`);
      console.error('BACKEND_URL used:', BACKEND_URL);
      setOptions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const debouncedSearch = useCallback(
    debounce(searchPlaces, 300),
    [searchPlaces]
  );

  useEffect(() => {
    debouncedSearch(inputValue);
  }, [inputValue, debouncedSearch]);

  const customStyles = {
    control: (provided, state) => ({
      ...provided,
      backgroundColor: 'rgb(51, 65, 85)',
      borderColor: state.isFocused ? 'rgb(249, 115, 22)' : 'rgb(71, 85, 105)',
      borderWidth: '1px',
      boxShadow: state.isFocused ? '0 0 0 3px rgba(249, 115, 22, 0.1)' : 'none',
      minHeight: '42px',
      '&:hover': {
        borderColor: 'rgb(249, 115, 22)',
      }
    }),
    input: (provided) => ({
      ...provided,
      color: 'white',
    }),
    placeholder: (provided) => ({
      ...provided,
      color: 'rgb(156, 163, 175)',
    }),
    singleValue: (provided) => ({
      ...provided,
      color: 'white',
    }),
    menu: (provided) => ({
      ...provided,
      backgroundColor: 'rgb(51, 65, 85)',
      border: '1px solid rgb(71, 85, 105)',
      boxShadow: '0 10px 25px rgba(0, 0, 0, 0.3)',
    }),
    menuList: (provided) => ({
      ...provided,
      backgroundColor: 'rgb(51, 65, 85)',
      maxHeight: '200px',
    }),
    option: (provided, state) => ({
      ...provided,
      backgroundColor: state.isFocused 
        ? 'rgb(71, 85, 105)' 
        : state.isSelected 
        ? 'rgb(249, 115, 22)' 
        : 'transparent',
      color: 'white',
      cursor: 'pointer',
      '&:hover': {
        backgroundColor: 'rgb(71, 85, 105)',
      }
    }),
    noOptionsMessage: (provided) => ({
      ...provided,
      color: 'rgb(156, 163, 175)',
    }),
    loadingMessage: (provided) => ({
      ...provided,
      color: 'rgb(156, 163, 175)',
    }),
    dropdownIndicator: (provided) => ({
      ...provided,
      color: 'rgb(156, 163, 175)',
      '&:hover': {
        color: 'rgb(249, 115, 22)',
      }
    }),
    clearIndicator: (provided) => ({
      ...provided,
      color: 'rgb(156, 163, 175)',
      '&:hover': {
        color: 'rgb(239, 68, 68)',
      }
    }),
  };

  const formatOptionLabel = (option) => (
    <div className="flex items-center gap-2 py-1">
      <MapPin className="h-4 w-4 text-orange-400 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-white text-sm font-medium truncate">
          {option.label}
        </div>
        {(option.region || option.country) && (
          <div className="text-gray-400 text-xs truncate">
            {[option.region, option.country].filter(Boolean).join(', ')}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className={className}>
      <Select
        value={value}
        onChange={onChange}
        onInputChange={setInputValue}
        options={options}
        styles={customStyles}
        formatOptionLabel={formatOptionLabel}
        placeholder={
          <div className="flex items-center gap-2 text-gray-400">
            <Search className="h-4 w-4" />
            {placeholder}
          </div>
        }
        noOptionsMessage={({ inputValue }) => 
          inputValue.length < 2 
            ? "Type at least 2 characters to search..."
            : isLoading 
            ? "Searching..."
            : "No places found"
        }
        loadingMessage={() => "Searching places..."}
        isLoading={isLoading}
        isClearable
        isSearchable
        menuPortalTarget={document.body}
        menuPlacement="auto"
        maxMenuHeight={200}
      />
    </div>
  );
};

// Debounce utility function
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

export default PlaceSearch;