# slack.py

import json
import secrets
import os
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import asyncio
import base64
from integrations.integration_item import IntegrationItem

from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = os.getenv('SLACK_CLIENT_ID', '9550160782374.9535999786983')
CLIENT_SECRET = os.getenv('SLACK_CLIENT_SECRET', 'your-slack-secret-here')
REDIRECT_URI = 'https://f6204becd38d.ngrok-free.app/integrations/slack/oauth2callback'
authorization_url = f'https://slack.com/oauth/v2/authorize?client_id={CLIENT_ID}&scope=users:read,channels:read,groups:read,im:read&redirect_uri={REDIRECT_URI}'

async def authorize_slack(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    encoded_state = json.dumps(state_data)
    await add_key_value_redis(f'slack_state:{org_id}:{user_id}', encoded_state, expire=600)

    return f'{authorization_url}&state={encoded_state}'

async def oauth2callback_slack(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error'))
    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    state_data = json.loads(encoded_state)

    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')

    saved_state = await get_value_redis(f'slack_state:{org_id}:{user_id}')

    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                'https://slack.com/api/oauth.v2.access',
                data={
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'code': code,
                    'redirect_uri': REDIRECT_URI
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            ),
            delete_key_redis(f'slack_state:{org_id}:{user_id}'),
        )

    await add_key_value_redis(f'slack_credentials:{org_id}:{user_id}', json.dumps(response.json()), expire=600)
    
    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)

async def get_slack_credentials(user_id, org_id):
    credentials = await get_value_redis(f'slack_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials)
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    await delete_key_redis(f'slack_credentials:{org_id}:{user_id}')

    return credentials

def create_integration_item_metadata_object(
    response_json: dict, item_type: str, parent_id=None, parent_name=None
) -> IntegrationItem:
    """Creates an integration metadata object from the Slack API response"""
    integration_item_metadata = IntegrationItem(
        id=response_json.get('id', None) + '_' + item_type if response_json.get('id') else None,
        name=response_json.get('name', response_json.get('real_name', 'Unknown')),
        type=item_type,
        parent_id=parent_id,
        parent_path_or_name=parent_name,
    )

    return integration_item_metadata

async def get_items_slack(credentials) -> list[IntegrationItem]:
    """Aggregates all metadata relevant for a Slack integration"""
    credentials = json.loads(credentials)
    access_token = credentials.get('access_token')
    list_of_integration_item_metadata = []

    async with httpx.AsyncClient() as client:
        # Run all API calls concurrently using asyncio.gather
        channels_response, users_response, dms_response = await asyncio.gather(
            # Fetch channels (public and private)
            client.get(
                'https://slack.com/api/conversations.list',
                headers={'Authorization': f'Bearer {access_token}'},
                params={'types': 'public_channel,private_channel'}
            ),
            # Fetch users
            client.get(
                'https://slack.com/api/users.list',
                headers={'Authorization': f'Bearer {access_token}'}
            ),
            # Fetch DMs (direct messages)
            client.get(
                'https://slack.com/api/conversations.list',
                headers={'Authorization': f'Bearer {access_token}'},
                params={'types': 'im'}
            )
        )

        # Process channels response
        if channels_response.status_code == 200:
            channels_data = channels_response.json()
            if channels_data.get('ok'):
                for channel in channels_data.get('channels', []):
                    list_of_integration_item_metadata.append(
                        create_integration_item_metadata_object(channel, 'Channel')
                    )

        # Process users response
        if users_response.status_code == 200:
            users_data = users_response.json()
            if users_data.get('ok'):
                for user in users_data.get('members', []):
                    if not user.get('deleted', False) and not user.get('is_bot', False):
                        list_of_integration_item_metadata.append(
                            create_integration_item_metadata_object(user, 'User')
                        )

        # Process DMs response
        if dms_response.status_code == 200:
            dms_data = dms_response.json()
            if dms_data.get('ok'):
                for dm in dms_data.get('channels', []):
                    list_of_integration_item_metadata.append(
                        create_integration_item_metadata_object(dm, 'DirectMessage')
                    )

    print(f'list_of_integration_item_metadata: {list_of_integration_item_metadata}')
    return list_of_integration_item_metadata