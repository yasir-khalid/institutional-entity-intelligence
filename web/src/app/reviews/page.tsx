import { Suspense } from "react";
import ReviewQueue from "@/components/ReviewQueue";
import { Loading } from "@/components/WorkspaceStates";
export default function ReviewsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ReviewQueue />
    </Suspense>
  );
}
