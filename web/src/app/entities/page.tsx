import EntityWorkspace from "@/components/EntityWorkspace";
import { firstValues, type PageSearchParams } from "@/lib/search-params";

export default async function EntitiesPage({
  searchParams,
}: {
  searchParams: PageSearchParams;
}) {
  return <EntityWorkspace searchParams={firstValues(await searchParams)} />;
}
