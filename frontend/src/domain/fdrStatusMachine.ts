import type { FDRStatus, Role } from '../types';
export interface Transition { from: FDRStatus; to: FDRStatus; roles: readonly (Role | 'system')[] }
export const transitions: readonly Transition[] = [
 {from:'Submitted',to:'Under Verification',roles:['institution_user','administrator','system']},
 {from:'Under Verification',to:'Query Raised',roles:['scrutiny_officer','administrator']},
 {from:'Under Verification',to:'Verified',roles:['scrutiny_officer','administrator']},
 {from:'Under Verification',to:'Rejected',roles:['scrutiny_officer','administrator']},
 {from:'Query Raised',to:'Corrected',roles:['institution_user']},
 {from:'Corrected',to:'Under Verification',roles:['institution_user']},
 {from:'Verified',to:'Active',roles:['system']},
 {from:'Active',to:'Nearing Maturity',roles:['system']},
 {from:'Nearing Maturity',to:'Matured',roles:['system']},
 {from:'Nearing Maturity',to:'Renewed',roles:['institution_user','scrutiny_officer']},
 {from:'Matured',to:'Renewed',roles:['institution_user','scrutiny_officer']},
 {from:'Matured',to:'Release Requested',roles:['institution_user']},
 {from:'Renewed',to:'Released / Closed',roles:['system']},
 {from:'Release Requested',to:'Released / Closed',roles:['administrator']},
 {from:'Release Requested',to:'Active',roles:['administrator']}
];
export function isTransitionAllowed(from: FDRStatus, to: FDRStatus, role: Role | 'system'): boolean { return transitions.some((item) => item.from === from && item.to === to && item.roles.includes(role)); }
