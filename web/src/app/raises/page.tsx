import OfferingFeed from "@/components/explore/OfferingFeed";
import { firstValues, type PageSearchParams } from "@/lib/search-params";

export default async function RaisesPage({
  searchParams,
}: {
  searchParams: PageSearchParams;
}) {
  return <OfferingFeed searchParams={firstValues(await searchParams)} />;
}
