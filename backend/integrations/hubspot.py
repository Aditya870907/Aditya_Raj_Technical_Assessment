# hubspot.py

import json
import secrets
import os
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import asyncio
import base64
import requests
from integrations.integration_item import IntegrationItem

from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = os.getenv('HUBSPOT_CLIENT_ID', 'caa42675-7ba3-4968-b1e9-6fce5eb64854')
CLIENT_SECRET = os.getenv('HUBSPOT_CLIENT_SECRET', 'your-hubspot-secret-here')
REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'
authorization_url = f'https://app.hubspot.com/oauth/authorize?client_id={CLIENT_ID}&scope=oauth%20crm.objects.contacts.read&redirect_uri={REDIRECT_URI}'

async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    encoded_state = json.dumps(state_data)
    await add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', encoded_state, expire=600)

    return f'{authorization_url}&state={encoded_state}'

async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error'))
    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    state_data = json.loads(encoded_state)

    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')

    saved_state = await get_value_redis(f'hubspot_state:{org_id}:{user_id}')

    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                'https://api.hubapi.com/oauth/v1/token',
                data={
                    'grant_type': 'authorization_code',
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'redirect_uri': REDIRECT_URI,
                    'code': code
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            ),
            delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
        )

    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(response.json()), expire=600)
    
    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)

async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials)
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')

    return credentials

def create_integration_item_metadata_object(
    response_json: dict, item_type: str, parent_id=None, parent_name=None
) -> IntegrationItem:
    """Creates an integration metadata object from the HubSpot API response"""
    properties = response_json.get('properties', {})
    
    # Get contact name from firstname and lastname or email
    first_name = properties.get('firstname', '')
    last_name = properties.get('lastname', '')
    email = properties.get('email', '')
    
    if first_name or last_name:
        contact_name = f"{first_name} {last_name}".strip()
    elif email:
        contact_name = email
    else:
        contact_name = 'Unknown Contact'
    
    integration_item_metadata = IntegrationItem(
        id=response_json.get('id', None) + '_' + item_type if response_json.get('id') else None,
        name=contact_name,
        type=item_type,
        parent_id=parent_id,
        parent_path_or_name=parent_name,
        creation_time=response_json.get('createdAt'),
        last_modified_time=response_json.get('updatedAt'),
    )

    return integration_item_metadata

async def get_items_hubspot(credentials) -> list[IntegrationItem]:
    """Aggregates all metadata relevant for a HubSpot integration"""
    credentials = json.loads(credentials)
    access_token = credentials.get('access_token')
    list_of_integration_item_metadata = []

    # Fetch contacts
    async with httpx.AsyncClient() as client:
        contacts_response = await client.get(
        'https://api.hubapi.com/crm/v3/objects/contacts',
        headers={'Authorization': f'Bearer {access_token}'},
        params={
            'limit': 100,
            'properties': 'firstname,lastname,email'
        }
    )

    if contacts_response.status_code == 200:
        contacts_data = contacts_response.json()
        for contact in contacts_data.get('results', []):
            list_of_integration_item_metadata.append(
                create_integration_item_metadata_object(contact, 'Contact')
            )

    print(f'list_of_integration_item_metadata: {list_of_integration_item_metadata}')
    return list_of_integration_item_metadata