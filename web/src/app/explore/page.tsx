import ExploreSearch from "@/components/explore/ExploreSearch";
import { firstValues, type PageSearchParams } from "@/lib/search-params";

export default async function ExplorePage({
  searchParams,
}: {
  searchParams: PageSearchParams;
}) {
  return <ExploreSearch searchParams={firstValues(await searchParams)} />;
}
