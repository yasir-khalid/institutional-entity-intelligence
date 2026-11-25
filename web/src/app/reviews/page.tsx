import ReviewQueue from "@/components/ReviewQueue";
import { firstValues, type PageSearchParams } from "@/lib/search-params";

export default async function ReviewsPage({
  searchParams,
}: {
  searchParams: PageSearchParams;
}) {
  return <ReviewQueue searchParams={firstValues(await searchParams)} />;
}
