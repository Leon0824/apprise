# -*- coding: utf-8 -*-
# BSD 3-Clause License
#
# Apprise - Push Notification Library.
# Copyright (c) 2023, Chris Caron <lead2gold@gmail.com>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import re
import requests
from json import dumps
import base64

from .NotifyBase import NotifyBase
from ..URLBase import PrivacyMode
from ..common import NotifyType
from ..utils import parse_list
from ..utils import validate_regex
from ..AppriseLocale import gettext_lazy as _


class NotifyAppriseAPI(NotifyBase):
    """
    A wrapper for Apprise (Persistent) API Notifications
    """

    # The default descriptive name associated with the Notification
    service_name = 'Apprise API'

    # The services URL
    service_url = 'https://github.com/caronc/apprise-api'

    # The default protocol
    protocol = 'apprise'

    # The default secure protocol
    secure_protocol = 'apprises'

    # A URL that takes you to the setup/help of the specific protocol
    setup_url = 'https://github.com/caronc/apprise/wiki/Notify_apprise_api'

    # Depending on the number of transactions/notifications taking place, this
    # could take a while. 30 seconds should be enough to perform the task
    socket_connect_timeout = 30.0

    # Disable throttle rate for Apprise API requests since they are normally
    # local anyway
    request_rate_per_sec = 0.0

    # Define object templates
    templates = (
        '{schema}://{host}/{token}',
        '{schema}://{host}:{port}/{token}',
        '{schema}://{user}@{host}/{token}',
        '{schema}://{user}@{host}:{port}/{token}',
        '{schema}://{user}:{password}@{host}/{token}',
        '{schema}://{user}:{password}@{host}:{port}/{token}',
    )

    # Define our tokens; these are the minimum tokens required required to
    # be passed into this function (as arguments). The syntax appends any
    # previously defined in the base package and builds onto them
    template_tokens = dict(NotifyBase.template_tokens, **{
        'host': {
            'name': _('Hostname'),
            'type': 'string',
            'required': True,
        },
        'port': {
            'name': _('Port'),
            'type': 'int',
            'min': 1,
            'max': 65535,
        },
        'user': {
            'name': _('Username'),
            'type': 'string',
        },
        'password': {
            'name': _('Password'),
            'type': 'string',
            'private': True,
        },
        'token': {
            'name': _('Token'),
            'type': 'string',
            'required': True,
            'private': True,
            'regex': (r'^[A-Z0-9_-]{1,32}$', 'i'),
        },
    })

    # Define our template arguments
    template_args = dict(NotifyBase.template_args, **{
        'tags': {
            'name': _('Tags'),
            'type': 'string',
        },
        'to': {
            'alias_of': 'token',
        },
    })

    # Define any kwargs we're using
    template_kwargs = {
        'headers': {
            'name': _('HTTP Header'),
            'prefix': '+',
        },
    }

    def __init__(self, token=None, tags=None, headers=None, **kwargs):
        """
        Initialize Apprise API Object

        headers can be a dictionary of key/value pairs that you want to
        additionally include as part of the server headers to post with

        """
        super().__init__(**kwargs)

        self.fullpath = kwargs.get('fullpath')
        if not isinstance(self.fullpath, str):
            self.fullpath = '/'

        self.token = validate_regex(
            token, *self.template_tokens['token']['regex'])
        if not self.token:
            msg = 'The Apprise API token specified ({}) is invalid.'\
                .format(token)
            self.logger.warning(msg)
            raise TypeError(msg)

        # Build list of tags
        self.__tags = parse_list(tags)

        self.headers = {}
        if headers:
            # Store our extra headers
            self.headers.update(headers)

        return

    def url(self, privacy=False, *args, **kwargs):
        """
        Returns the URL built dynamically based on specified arguments.
        """

        # Our URL parameters
        params = self.url_parameters(privacy=privacy, *args, **kwargs)

        # Append our headers into our parameters
        params.update({'+{}'.format(k): v for k, v in self.headers.items()})

        if self.__tags:
            params['tags'] = ','.join([x for x in self.__tags])

        # Determine Authentication
        auth = ''
        if self.user and self.password:
            auth = '{user}:{password}@'.format(
                user=NotifyAppriseAPI.quote(self.user, safe=''),
                password=self.pprint(
                    self.password, privacy, mode=PrivacyMode.Secret, safe=''),
            )
        elif self.user:
            auth = '{user}@'.format(
                user=NotifyAppriseAPI.quote(self.user, safe=''),
            )

        default_port = 443 if self.secure else 80

        fullpath = self.fullpath.strip('/')
        return '{schema}://{auth}{hostname}{port}{fullpath}{token}' \
               '/?{params}'.format(
                   schema=self.secure_protocol
                   if self.secure else self.protocol,
                   auth=auth,
                   # never encode hostname since we're expecting it to be a
                   # valid one
                   hostname=self.host,
                   port='' if self.port is None or self.port == default_port
                        else ':{}'.format(self.port),
                   fullpath='/{}/'.format(NotifyAppriseAPI.quote(
                       fullpath, safe='/')) if fullpath else '/',
                   token=self.pprint(self.token, privacy, safe=''),
                   params=NotifyAppriseAPI.urlencode(params))

    def send(self, body, title='', notify_type=NotifyType.INFO, attach=None,
             **kwargs):
        """
        Perform Apprise API Notification
        """

        # Prepare HTTP Headers
        headers = {
            'User-Agent': self.app_id,
            'Content-Type': 'application/json'
        }

        # Apply any/all header over-rides defined
        headers.update(self.headers)

        # Track our potential attachments
        attachments = []
        if attach:
            for attachment in attach:
                # Perform some simple error checking
                if not attachment:
                    # We could not access the attachment
                    self.logger.error(
                        'Could not access attachment {}.'.format(
                            attachment.url(privacy=True)))
                    return False

                try:
                    with open(attachment.path, 'rb') as f:
                        # Output must be in a DataURL format (that's what
                        # PushSafer calls it):
                        attachments.append({
                            'filename': attachment.name,
                            'base64': base64.b64encode(f.read())
                            .decode('utf-8'),
                            'mimetype': attachment.mimetype,
                        })

                except (OSError, IOError) as e:
                    self.logger.warning(
                        'An I/O error occurred while reading {}.'.format(
                            attachment.name if attachment else 'attachment'))
                    self.logger.debug('I/O Exception: %s' % str(e))
                    return False

        # prepare Apprise API Object
        payload = {
            # Apprise API Payload
            'title': title,
            'body': body,
            'type': notify_type,
            'format': self.notify_format,
            'attachments': attachments,
        }

        if self.__tags:
            payload['tag'] = self.__tags

        auth = None
        if self.user:
            auth = (self.user, self.password)

        # Set our schema
        schema = 'https' if self.secure else 'http'

        url = '%s://%s' % (schema, self.host)
        if isinstance(self.port, int):
            url += ':%d' % self.port

        fullpath = self.fullpath.strip('/')
        url += '/{}/'.format(fullpath) if fullpath else '/'
        url += 'notify/{}'.format(self.token)

        # Some entries can not be over-ridden
        headers.update({
            'User-Agent': self.app_id,
            'Content-Type': 'application/json',
            # Pass our Source UUID4 Identifier
            'X-Apprise-ID': self.asset._uid,
            # Pass our current recursion count to our upstream server
            'X-Apprise-Recursion-Count': str(self.asset._recursion + 1),
        })

        self.logger.debug('Apprise API POST URL: %s (cert_verify=%r)' % (
            url, self.verify_certificate,
        ))
        self.logger.debug('Apprise API Payload: %s' % str(payload))

        # Always call throttle before any remote server i/o is made
        self.throttle()

        try:
            r = requests.post(
                url,
                data=dumps(payload),
                headers=headers,
                auth=auth,
                verify=self.verify_certificate,
                timeout=self.request_timeout,
            )
            if r.status_code != requests.codes.ok:
                # We had a problem
                status_str = \
                    NotifyAppriseAPI.http_response_code_lookup(r.status_code)

                self.logger.warning(
                    'Failed to send Apprise API notification: '
                    '{}{}error={}.'.format(
                        status_str,
                        ', ' if status_str else '',
                        r.status_code))

                self.logger.debug('Response Details:\r\n{}'.format(r.content))

                # Return; we're done
                return False

            else:
                self.logger.info('Sent Apprise API notification.')

        except requests.RequestException as e:
            self.logger.warning(
                'A Connection error occurred sending Apprise API '
                'notification to %s.' % self.host)
            self.logger.debug('Socket Exception: %s' % str(e))

            # Return; we're done
            return False

        return True

    @staticmethod
    def parse_native_url(url):
        """
        Support http://hostname/notify/token and
                http://hostname/path/notify/token
        """

        result = re.match(
            r'^http(?P<secure>s?)://(?P<hostname>[A-Z0-9._-]+)'
            r'(:(?P<port>[0-9]+))?'
            r'(?P<path>/[^?]+?)?/notify/(?P<token>[A-Z0-9_-]{1,32})/?'
            r'(?P<params>\?.+)?$', url, re.I)

        if result:
            return NotifyAppriseAPI.parse_url(
                '{schema}://{hostname}{port}{path}/{token}/{params}'.format(
                    schema=NotifyAppriseAPI.secure_protocol
                    if result.group('secure') else NotifyAppriseAPI.protocol,
                    hostname=result.group('hostname'),
                    port='' if not result.group('port')
                    else ':{}'.format(result.group('port')),
                    path='' if not result.group('path')
                    else result.group('path'),
                    token=result.group('token'),
                    params='' if not result.group('params')
                    else '?{}'.format(result.group('params'))))

        return None

    @staticmethod
    def parse_url(url):
        """
        Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object.

        """
        results = NotifyBase.parse_url(url)
        if not results:
            # We're done early as we couldn't load the results
            return results

        # Add our headers that the user can potentially over-ride if they wish
        # to to our returned result set and tidy entries by unquoting them
        results['headers'] = \
            {NotifyAppriseAPI.unquote(x): NotifyAppriseAPI.unquote(y)
             for x, y in results['qsd+'].items()}

        # Support the passing of tags in the URL
        if 'tags' in results['qsd'] and len(results['qsd']['tags']):
            results['tags'] = \
                NotifyAppriseAPI.parse_list(results['qsd']['tags'])

        # Support the 'to' & 'token' variable so that we can support rooms
        # this way too.
        if 'token' in results['qsd'] and len(results['qsd']['token']):
            results['token'] = \
                NotifyAppriseAPI.unquote(results['qsd']['token'])

        elif 'to' in results['qsd'] and len(results['qsd']['to']):
            results['token'] = NotifyAppriseAPI.unquote(results['qsd']['to'])

        else:
            # Start with a list of path entries to work with
            entries = NotifyAppriseAPI.split_path(results['fullpath'])
            if entries:
                # use our last entry found
                results['token'] = entries[-1]

                # pop our last entry off
                entries = entries[:-1]

                # re-assemble our full path
                results['fullpath'] = '/'.join(entries)

        return results
