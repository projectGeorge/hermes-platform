import { SignIn } from "@clerk/react";

import { AuthPageFrame } from "./AuthPageFrame";
import { clerkAppearance } from "./clerkAppearance";

export function SignInPage() {
  return (
    <AuthPageFrame tagline="Return to intake review, order control, and carrier booking inside one premium operator workspace.">
      <SignIn appearance={clerkAppearance} path="/sign-in" routing="path" signUpUrl="/sign-up" />
    </AuthPageFrame>
  );
}
