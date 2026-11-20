import {createHostedApiProvider} from '../northpoint/api/hosted-api.js';
import {allowsRequest,isMobileAccessRequest} from './permissions.js';

const provider = createHostedApiProvider();
export const dataSource = {
  ...provider,
  async request(options) {
    if (!allowsRequest(options)) {
      throw Object.assign(new Error('Your account cannot access this resource.'), {status:403});
    }
    const {READ_ONLY_PREVIEW, MOBILE_ACCESS_TESTING} = globalThis.NORTHPOINT_CONFIG;
    const isTestWrite = MOBILE_ACCESS_TESTING === true && isMobileAccessRequest(options);
    if (READ_ONLY_PREVIEW && (options.method ?? 'GET') !== 'GET' && !isTestWrite) {
      throw Object.assign(new Error('Development preview is read-only. No changes were saved.'), {status:403});
    }
    return provider.request(options);
  }
};
