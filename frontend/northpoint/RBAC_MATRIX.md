# Northpoint — Role-Based Access Control (RBAC)

## Overview

This document defines the feature access permissions for the four user roles in the Northpoint HR Violation Tracker:

1. HR
2. Supervisor
3. Chief Manager
4. Concerned Employee

Each role has specific permissions that determine which features they can access and which actions they can perform.

## Access Control Matrix

| Feature | HR | Supervisor | Chief Manager | Concerned Employee |
|---|---|---|---|---|
| View the dashboard | Yes | Yes | Yes | No |
| Add and edit employees | Yes | No | No | No |
| Manage violation types | Yes | No | No | No |
| Log a violation | Yes | Yes | No | No |
| View all violations | Yes | Yes | Yes | No |
| View personal employee violations | Yes | Yes | Yes | Yes |
| Remove a violation | Yes | No | No | No |
| View the removal log | Yes | No | Yes | No |
| View activity and analytics | Yes | No | Yes | No |
| Submit a proof photo | No | Yes | No | No |
| View proof photos | Yes | Yes | No | No |
| View location data and paths | Yes | No | No | No |
| Manage employee mobile app accounts | Yes | No | No | No |
| Permanently delete employees | Yes | No | No | No |
| Edit issued violation details | Yes | No | No | No |
| Edit, rename, or delete existing proof photos | Yes | No | No | No |

## Role Permissions

### HR
- View the dashboard
- Add and edit employees
- Manage violation types
- Log violations
- View all violations
- View personal employee violations
- Remove violations
- View the removal log
- View activity and analytics
- View proof photos
- View location data and paths
- Manage employee mobile app accounts
- Permanently delete employees
- Edit issued violation details
- Edit, rename, or delete existing proof photos

### Supervisor
- View the dashboard
- Log violations
- View all violations
- View personal employee violations
- Submit proof photos
- View proof photos

### Chief Manager
- View the dashboard
- View all violations
- View personal employee violations
- View the removal log
- View activity and analytics

### Concerned Employee
- View personal employee violations only

## Implementation Requirements

- Access permissions must follow the matrix exactly.
- Users must only see and interact with features permitted for their role.
- Unauthorized features and actions must not be accessible through frontend navigation.
- Role identification must come from the authenticated backend session.
- The backend must enforce authorization for all protected API operations.
- Concerned Employees must only be able to retrieve their own violation records.
- Shared functionality should be reused across role-specific interfaces.
- HR keeps existing management features unless the matrix explicitly denies them. Unspecified permissions remain denied for other roles. Frontend access uses known actions and API routes, with authorization enforced by the server.