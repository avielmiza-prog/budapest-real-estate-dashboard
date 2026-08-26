import { PasscodeGate } from "@/components/auth/passcode-gate";
import { Dashboard } from "@/components/dashboard/dashboard";

export default function Home() {
  return (
    <PasscodeGate>
      <Dashboard />
    </PasscodeGate>
  );
}
