import { createPreviewProvider } from './preview-provider.js';
// The only integration switch. A future backend adapter implements the same
// request({path,method,query,body,actor,signal}) interface. Never use preview
// records as a fallback if that adapter fails. See INTEGRATION.md.
export const dataSource=createPreviewProvider();
export const sourceLabel='v.FE-1.0';
export const sourceNotice='';
