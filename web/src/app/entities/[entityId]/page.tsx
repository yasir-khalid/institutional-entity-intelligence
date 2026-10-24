import { Suspense } from "react";
import EntityPage from "@/components/EntityPage";
import { Loading } from "@/components/WorkspaceStates";

export default async function EntityRoute({
  params,
}: {
  params: Promise<{ entityId: string }>;
}) {
  const { entityId } = await params;
  return (
    <Suspense fallback={<Loading />}>
      <EntityPage key={entityId} id={entityId} />
    </Suspense>
  );
}
