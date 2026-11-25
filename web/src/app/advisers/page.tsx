import AdviserDirectory from "@/components/explore/AdviserDirectory";
import { firstValues, type PageSearchParams } from "@/lib/search-params";

export default async function AdvisersPage({
  searchParams,
}: {
  searchParams: PageSearchParams;
}) {
  return <AdviserDirectory searchParams={firstValues(await searchParams)} />;
}
