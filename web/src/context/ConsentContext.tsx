import { createContext, useContext, useState } from "react";
import { isConsentAccepted, setConsentAccepted } from "../lib/storage";

interface ConsentContextValue {
  accepted: boolean;
  accept: () => void;
}

const ConsentContext = createContext<ConsentContextValue | null>(null);

export function ConsentProvider({ children }: { children: React.ReactNode }) {
  const [accepted, setAccepted] = useState<boolean>(() => isConsentAccepted());

  const accept = () => {
    setConsentAccepted();
    setAccepted(true);
  };

  return <ConsentContext.Provider value={{ accepted, accept }}>{children}</ConsentContext.Provider>;
}

export function useConsent() {
  const value = useContext(ConsentContext);
  if (!value) {
    throw new Error("useConsent must be used inside ConsentProvider");
  }
  return value;
}
