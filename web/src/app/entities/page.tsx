import { Suspense } from "react";
import EntityWorkspace from "@/components/EntityWorkspace";
import { Loading } from "@/components/WorkspaceStates";

export default function EntitiesPage() {
  return (
    <Suspense fallback={<Loading />}>
      <EntityWorkspace />
    </Suspense>
  );
}
