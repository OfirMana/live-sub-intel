"""Foundry configuration and non-secret, actionable failure classification."""
from dataclasses import dataclass, field
import os
import re
import importlib.metadata
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError

ENV_NAMES=('FOUNDRY_ENDPOINT','FOUNDRY_API_KEY','FOUNDRY_DEPLOYMENT')
SELECTION_FIELDS=('fact_ids','style')


def runtime_versions():
    versions={}
    for name in ('openai','httpx','httpx2','pydantic'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    return versions


class FoundryConfigError(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__(code)  # Never embed the offending value.


def normalize_endpoint(endpoint):
    value=endpoint.strip()
    try:parts=urlsplit(value);port=parts.port
    except ValueError:raise FoundryConfigError('CONFIG_ENDPOINT_FORMAT') from None
    if parts.scheme!='https' or not parts.hostname:
        raise FoundryConfigError('CONFIG_ENDPOINT_FORMAT')
    if parts.username or parts.password or parts.query or parts.fragment:
        raise FoundryConfigError('CONFIG_ENDPOINT_FORMAT')
    if not parts.hostname.isascii() or any(c.isspace() for c in parts.netloc):
        raise FoundryConfigError('CONFIG_ENDPOINT_FORMAT')
    # Only inspect the PATH. '/openai' in an 'openai-...' hostname is not a path.
    path=parts.path.rstrip('/')
    if path and not (path=='/openai' or path.startswith('/openai/') or path.startswith('/api/projects/')):
        raise FoundryConfigError('CONFIG_ENDPOINT_PATH')
    return urlunsplit((parts.scheme,parts.netloc,'/openai/v1/','',''))


@dataclass(frozen=True)
class FoundryConfig:
    base_url:str
    deployment:str
    api_key:str=field(repr=False)


def read_config():
    endpoint,key,deployment=((os.environ.get(name) or '').strip() for name in ENV_NAMES)
    if not all((endpoint,key,deployment)):return None
    base_url=normalize_endpoint(endpoint)
    if not key.isascii() or any(c.isspace() or ord(c)<33 for c in key) or any(c in key for c in '\'"'):
        raise FoundryConfigError('CONFIG_KEY_FORMAT')
    if not deployment.isascii() or not re.fullmatch(r'[\w.-]+',deployment,re.ASCII):
        raise FoundryConfigError('CONFIG_DEPLOYMENT_FORMAT')
    return FoundryConfig(base_url,deployment,key)


def configuration_summary(include_endpoint=False):
    missing=[name for name in ENV_NAMES if not (os.environ.get(name) or '').strip()]
    result=dict(configured=False,missing=missing)
    if missing:return result
    try:config=read_config()
    except FoundryConfigError as error:
        result['code']=error.code
        return result
    result.update(configured=True,code='CONFIG_VALID')
    if include_endpoint:result.update(base_url=config.base_url,deployment=config.deployment)
    return result


HINTS={
 'CONFIG_ENDPOINT_FORMAT':'Use the HTTPS resource/project endpoint, without quotes, credentials or a query string.',
 'CONFIG_ENDPOINT_PATH':'Use the resource root, its /openai/v1/ URL, or the Foundry project endpoint.',
 'CONFIG_KEY_FORMAT':'Copy the resource key as one ASCII value, without quotes, internal whitespace or line breaks.',
 'CONFIG_DEPLOYMENT_FORMAT':'Use the deployment NAME from this resource, without quotes, spaces or a URL.',
 'SDK_NOT_INSTALLED':'Install the runtime requirements in the actual App Service environment.',
 'SDK_CONFIGURATION_ERROR':'Check the installed SDK version and client/request options in the running container.',
 'AUTHENTICATION_FAILED':'Verify the key belongs to this endpoint resource and Azure App settings use the current regenerated key.',
 'RESOURCE_ACCESS_DENIED':'Check resource network/firewall rules and the authentication/access policy from App Service.',
 'DEPLOYMENT_OR_ROUTE_NOT_FOUND':'Verify endpoint, deployment name and deployed model on the same resource.',
 'PROVIDER_BAD_REQUEST':'Inspect the safe provider error code/request ID; check model support for request parameters.',
 'PROVIDER_RATE_LIMIT_OR_QUOTA':'Check the deployment quota, billing and rate limits.',
 'PROVIDER_SERVICE_ERROR':'The provider failed; check service status and retry after cooldown.',
 'DNS_LOOKUP_FAILED':'Check the actual endpoint hostname and DNS/private endpoint routing from App Service.',
 'TLS_VERIFICATION_FAILED':'Check hostname, trusted CA certificates and TLS proxy settings; keep certificate verification enabled.',
 'NETWORK_TIMEOUT':'Check outbound routing and provider latency from the actual App Service runtime.',
 'CONNECTION_FAILED':'Check outbound HTTPS, proxy settings, DNS and the nested transport category in the runtime.',
 'MODEL_RESPONSE_REJECTED':'The provider replied, but the result did not match the allowed fact-selection schema.',
 'UNEXPECTED_CLIENT_ERROR':'Run the runtime doctor and inspect SDK/client setup without printing credentials.',
}


def validation_summary(error):
    """Pydantic error kinds and field paths only: never the input, its values or messages."""
    if not isinstance(error,ValidationError):return None
    return [dict(type=item['type'],loc='.'.join(str(p) if isinstance(p,int) or p in SELECTION_FIELDS else 'unexpected_field' for p in item['loc']))
            for item in error.errors(include_url=False,include_context=False,include_input=False)[:5]]


def classify_failure(error,stage):
    chain=[];seen=set();item=error
    while item is not None and id(item) not in seen and len(chain)<8:
        seen.add(id(item));chain.append(item);item=item.__cause__ or item.__context__
    types=[type(item).__name__ for item in chain]
    # Messages are used for classification ONLY: never returned or logged.
    text=' '.join(str(item).lower() for item in chain)
    status=getattr(error,'status_code',None)
    if not isinstance(status,int):status=None
    if isinstance(error,FoundryConfigError):code=error.code
    elif stage=='output_validation':code='MODEL_RESPONSE_REJECTED'
    elif isinstance(error,ModuleNotFoundError):code='SDK_NOT_INSTALLED'
    elif status is not None:
        code={400:'PROVIDER_BAD_REQUEST',401:'AUTHENTICATION_FAILED',403:'RESOURCE_ACCESS_DENIED',404:'DEPLOYMENT_OR_ROUTE_NOT_FOUND',429:'PROVIDER_RATE_LIMIT_OR_QUOTA'}.get(status,'PROVIDER_SERVICE_ERROR' if status>=500 else 'UNEXPECTED_CLIENT_ERROR')
    elif any('ssl' in name.lower() or 'certificate' in name.lower() for name in types) or 'certificate_verify_failed' in text:
        code='TLS_VERIFICATION_FAILED'
    elif 'gaierror' in types or any(token in text for token in ('getaddrinfo failed','name or service not known','nodename nor servname','temporary failure in name resolution')):
        code='DNS_LOOKUP_FAILED'
    elif any('timeout' in name.lower() for name in types):code='NETWORK_TIMEOUT'
    elif any('connect' in name.lower() for name in types):code='CONNECTION_FAILED'
    elif stage in ('configuration','client_setup') or isinstance(error,TypeError):code='SDK_CONFIGURATION_ERROR'
    else:code='UNEXPECTED_CLIENT_ERROR'
    provider_code=getattr(error,'code',None)
    if provider_code not in ('unsupported_parameter','unsupported_value','context_length_exceeded','content_filter','insufficient_quota','rate_limit_exceeded','DeploymentNotFound','OperationNotSupported'):
        provider_code=None
    provider_param=getattr(error,'param',None)
    if provider_param not in ('model','messages','response_format','max_completion_tokens','max_tokens','temperature','top_p'):
        provider_param=None
    return dict(code=code,stage=stage,status=status,provider_code=provider_code,provider_param=provider_param,
                exception_type=type(error).__name__,cause_types=types[1:],validation_errors=validation_summary(error),
                hint=HINTS[code],retryable=code in ('NETWORK_TIMEOUT','CONNECTION_FAILED','PROVIDER_SERVICE_ERROR','PROVIDER_RATE_LIMIT_OR_QUOTA'))
