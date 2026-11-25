import EntityPage from "@/components/EntityPage";
import { firstValues, type PageSearchParams } from "@/lib/search-params";

export default async function EntityRoute({
  params,
  searchParams,
}: {
  params: Promise<{ entityId: string }>;
  searchParams: PageSearchParams;
}) {
  const { entityId } = await params;
  return (
    <EntityPage
      key={entityId}
      id={entityId}
      searchParams={firstValues(await searchParams)}
    />
  );
}
