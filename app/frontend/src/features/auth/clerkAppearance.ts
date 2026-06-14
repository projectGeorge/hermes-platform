/**
 * Clerk appearance configuration — Hermes Carbon + Amber design system.
 * Applied to <SignIn>, <SignUp>, and <UserButton> to replace Clerk's default teal/cyan palette.
 */

const hermesVariables = {
  // Amber replaces cyan/teal as the primary accent
  colorPrimary: "#f59e0b",
  // Card + modal background matches --hermes-bg-elevated
  colorBackground: "#131318",
  // Neutral gray for dividers, secondary borders
  colorNeutral: "#3f3f4a",
  // Text
  colorText: "#f0f0f4",
  colorTextSecondary: "#7c7c8a",
  // Inputs
  colorInputBackground: "#070d13",
  colorInputText: "#f0f0f4",
  // Semantic
  colorDanger: "#f87171",
  colorSuccess: "#34d399",
  // Shape + typography
  borderRadius: "0.5rem",
  fontFamily: '"IBM Plex Sans", ui-sans-serif, system-ui, sans-serif',
  fontSize: "14px",
} as const;

export const clerkAppearance = {
  variables: hermesVariables,
  elements: {
    // Give Clerk's own card the same border + shadow the old outer wrapper had
    card: {
      border: "1px solid rgba(255,255,255,0.07)",
      boxShadow: "0 24px 80px rgba(0,0,0,0.32)",
    },
    // Primary action button — amber gradient matching hermes-primary-button
    formButtonPrimary: {
      background: "linear-gradient(135deg, #f59e0b 0%, #f97316 100%)",
      color: "#0c0c10",
      fontWeight: "700",
    },
    // Social button (Google, etc.) — dark ghost style
    socialButtonsBlockButton: {
      border: "1px solid rgba(255,255,255,0.10)",
      backgroundColor: "rgba(255,255,255,0.03)",
      color: "#e2e8f0",
    },
    socialButtonsBlockButtonText: {
      color: "#e2e8f0",
    },
    // Footer links ("Sign in" / "Sign up")
    footerActionLink: {
      color: "#f59e0b",
    },
    // Internal links (forgot password, etc.)
    identityPreviewEditButton: {
      color: "#f59e0b",
    },
  },
} as const;

/** Appearance config for <UserButton> — targets the profile dropdown popup and the Manage Account modal. */
export const userButtonAppearance = {
  variables: hermesVariables,
  elements: {
    // ── Dropdown popup ───────────────────────────────────────────────────────
    userButtonPopoverCard: {
      backgroundColor: "#131318",
      border: "1px solid rgba(255,255,255,0.07)",
      boxShadow: "0 16px 64px rgba(0,0,0,0.50)",
      borderRadius: "0.75rem",
    },
    userButtonPopoverActionButton: {
      color: "#e2e8f0",
      borderRadius: "0.5rem",
    },
    userButtonPopoverActionButtonText: {
      color: "#e2e8f0",
    },
    userButtonPopoverActionButtonIcon: {
      color: "#7c7c8a",
    },
    userButtonPopoverFooter: {
      borderTop: "1px solid rgba(255,255,255,0.06)",
      backgroundColor: "transparent",
    },
    userButtonPopoverFooterText: {
      color: "#4b4b5a",
    },
    userButtonPopoverFooterLink: {
      color: "#6b6b7a",
    },
    userButtonAvatarBox: {
      borderRadius: "9999px",
    },

    // ── Manage Account modal ─────────────────────────────────────────────────

    // Outer modal card
    card: {
      backgroundColor: "#131318",
      border: "1px solid rgba(255,255,255,0.07)",
      boxShadow: "0 24px 80px rgba(0,0,0,0.50)",
      borderRadius: "0.75rem",
    },
    // Left navigation rail
    navbar: {
      backgroundColor: "#0c0c10",
      borderRight: "1px solid rgba(255,255,255,0.06)",
    },
    navbarButton: {
      color: "#7c7c8a",
      borderRadius: "0.5rem",
    },
    navbarButtonIcon: {
      color: "#7c7c8a",
    },
    // Scrollable page content
    pageScrollBox: {
      backgroundColor: "#131318",
    },
    // Section dividers
    profileSection: {
      borderTop: "1px solid rgba(255,255,255,0.06)",
    },
    profileSectionTitle: {
      borderBottom: "1px solid rgba(255,255,255,0.06)",
    },
    profileSectionTitleText: {
      color: "#7c7c8a",
      fontWeight: "600",
      textTransform: "uppercase" as const,
      letterSpacing: "0.1em",
      fontSize: "0.65rem",
    },
    // "Edit", "Add", "Remove" links inside sections
    profileSectionPrimaryButton: {
      color: "#f59e0b",
    },
    // Badges ("Default", "Unverified", etc.)
    badge: {
      backgroundColor: "rgba(245,158,11,0.10)",
      color: "#f59e0b",
      border: "1px solid rgba(245,158,11,0.20)",
    },
    // Form buttons
    formButtonPrimary: {
      background: "linear-gradient(135deg, #f59e0b 0%, #f97316 100%)",
      color: "#0c0c10",
      fontWeight: "700",
    },
    formButtonReset: {
      color: "#7c7c8a",
      border: "1px solid rgba(255,255,255,0.08)",
    },
    // Inline action menus (three-dot dropdowns)
    menuList: {
      backgroundColor: "#1a1a22",
      border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: "0.5rem",
      boxShadow: "0 8px 32px rgba(0,0,0,0.40)",
    },
    menuItem: {
      color: "#e2e8f0",
    },
    // Destructive menu item ("Remove", "Delete")
    menuItemDestructive: {
      color: "#f87171",
    },
    // Accordion rows (security, connected accounts)
    accordionTriggerButton: {
      color: "#e2e8f0",
    },
  },
} as const;
