import SecurityDirectory from "@/components/explore/SecurityDirectory";
import { firstValues, type PageSearchParams } from "@/lib/search-params";

export default async function SecuritiesPage({
  searchParams,
}: {
  searchParams: PageSearchParams;
}) {
  return <SecurityDirectory searchParams={firstValues(await searchParams)} />;
}
