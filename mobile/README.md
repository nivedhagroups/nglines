# Nivedha Groups Mobile

React Native + TypeScript app using Expo development builds, React Navigation, TanStack Query, React Hook Form/Zod, SecureStore, native image picker, and FCM device tokens.

## Setup

1. Install Node.js 20 or newer, then install dependencies with `npm install`.
2. Copy `.env.example` to `.env`. For Android emulator use `http://10.0.2.2:8000/api/v1`; for iOS simulator use `http://localhost:8000/api/v1`; for a physical phone use the development machine's LAN address.
3. Start the backend and apply its Alembic migrations, then bootstrap Chamber Bricks and the initial Super Admin as described in `docs/backend-setup.md`.
4. Generate native projects and install the development client with `npx expo prebuild`.
5. Run `npm run android` on a machine with Android Studio/SDK. Run `npm run ios` on macOS with Xcode.

`react-native-share` and FCM use native modules; use an Expo development build, not Expo Go. Configure APNs and Firebase credentials before enabling push delivery in production. Native build/signing credentials and store metadata are handled in the deployment deliverable.

## Implemented mobile workflows

- OTP login, persisted secure tokens, refresh, logout, and business selection.
- Role-aware More menu, Super Admin audit access, global settings/user links, and doubtful-transaction actions for CEO/Super Admin.
- Dashboard sales/expense periods, invoice/estimate/expense creation, customer search and purchase history, profile editing and picture capture/library upload, and bill-photo attachments.
- React Query retries, network awareness, loading/empty/error states, cursor-based list loading, and business-keyed cache invalidation.