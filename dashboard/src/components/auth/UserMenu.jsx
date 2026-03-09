/**
 * Auth: UserMenu — User avatar with dropdown menu.
 */

export default function UserMenu({ user, onSignOut }) {
  return (
    <div className="relative">
      <button className="flex items-center gap-2 rounded-full hover:bg-muted p-1">
        <img
          src={user?.photoURL || ''}
          alt={user?.displayName || 'User'}
          className="h-8 w-8 rounded-full"
          referrerPolicy="no-referrer"
        />
      </button>
      {/* TODO: Dropdown with: Profile, Settings, Sign Out */}
    </div>
  );
}
