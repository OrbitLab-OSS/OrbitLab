"""Compute Autoscaling Pages."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.pages.compute.layout import compute_page


@rx.page("/compute/autoscaling")
@compute_page
def autoscaling_page() -> rx.Component:
    return rx.el.div(
        components.PageHeader(
            "Autoscaling Pools",
        ),
        class_name="w-full h-full",
    )


# Autoscaling should be managed by an app lifecycle event
# The AutoscalingManager should load the configs for all pools (user UI changes will trigger the process to reload via
# an thread-supported Event object).
# It begins monitoring all nodes in a pool using configured health checks and specified intervals.
# If pool capacity changes are necessary, aquire a lease-lock on the pool (PMCFS/locks/pools/POOLID.lease).
# A lease lock should have a short TTL. On success, the lock is released. On failure, the lock is released. On crash,
# the TTL will allow another node to proceed with necessary mutations once the lock is expired.
# Since maintaining a static reference in the manifest to instances in the pool created too much IO churn, use the API
# to check the pool capacity at set intervals. In CLUSTER mode, the only change should be an HA Group is explicitly
# tied to the pool.
