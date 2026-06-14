import { SignUp } from "@clerk/react";

import { AuthPageFrame } from "./AuthPageFrame";
import { clerkAppearance } from "./clerkAppearance";

export function SignUpPage() {
  return (
    <AuthPageFrame tagline="Create your operator workspace and start managing freight loads inside one precise workflow shell.">
      <SignUp appearance={clerkAppearance} path="/sign-up" routing="path" signInUrl="/sign-in" />
    </AuthPageFrame>
  );
}
